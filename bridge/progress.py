"""Claude Code 도구 사용 → 작업 단계·진행도(%) 추정

AI는 실제 진행률을 알려주지 않으므로, 지금 쓰는 도구로 "어느 단계인지"를 추정합니다.

    단계          근거                                  진행도
    READING      요청 직후, 파일 읽기·검색·웹 조회         0–20
    PLANNING     할 일 목록·계획 작성                     20–30
    BUILDING     파일 쓰기·수정, 명령 실행(보기 전용 제외)   50–60
    REVIEWING    수정 이후의 테스트·빌드·검사 명령          80–90

- 단계는 앞으로만 갑니다(검토 중에 파일을 다시 읽어도 내려가지 않음).
- 단계 안에서는 시간이 지날수록 상한에 천천히 가까워집니다(멈춰 보이지 않게).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Phase:
    key: str
    label: str  # LCD 표시용 (영문, 11자 이하)
    lo: int
    hi: int


PHASES = (
    Phase("read", "READING", 0, 20),
    Phase("plan", "PLANNING", 20, 30),
    Phase("build", "BUILDING", 50, 60),
    Phase("review", "REVIEWING", 80, 90),
)
READ, PLAN, BUILD, REVIEW = range(4)

READ_TOOLS = {
    "Read", "Grep", "Glob", "LS", "WebFetch", "WebSearch", "NotebookRead",
    "ToolSearch", "ListMcpResourcesTool", "ReadMcpResourceTool",
}
PLAN_TOOLS = {"TodoWrite", "TaskCreate", "TaskUpdate", "EnterPlanMode"}
EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash", "PowerShell"}
# 이 도구가 나오면 사용자의 답을 기다리는 중
INPUT_TOOLS = {"AskUserQuestion", "ExitPlanMode"}

# 수정 이후 이런 명령을 실행하면 "검토" 단계로 봄
CHECK_RE = re.compile(
    r"\b(pytest|unittest|py_compile|mypy|ruff|flake8|pylint|"
    r"npm\s+(run\s+)?(test|build|lint)|yarn\s+(test|build|lint)|pnpm\s+(test|build|lint)|"
    r"tsc|eslint|jest|vitest|playwright|"
    r"cargo\s+(test|build|check|clippy)|go\s+(test|build|vet)|"
    r"dotnet\s+(test|build)|mvn|gradle|make|"
    r"arduino-cli\s+compile|git\s+(diff|status))\b",
    re.IGNORECASE,
)


# 보기만 하는 명령 (목록·내용·상태 확인). 이것만으로 된 명령은 "파악" 단계로 봄
LOOK_CMDS = {
    "ls", "dir", "cat", "head", "tail", "less", "more", "grep", "rg", "find", "tree", "wc",
    "pwd", "echo", "which", "where", "type", "stat", "file", "du", "df", "date", "whoami",
    "env", "printenv", "sort", "uniq", "cut", "awk", "sed", "jq", "diff", "netstat", "tasklist",
    "get-childitem", "get-content", "get-item", "get-process", "get-command", "select-string",
    "test-path", "format-table", "select-object", "where-object", "measure-object", "out-string",
}
LOOK_SUBCMDS = re.compile(
    r"^(git\s+(log|show|status|diff|branch|remote)|pip\s+(list|show|freeze)|"
    r"python3?\s+(--version|-V)|node\s+(--version|-v)|npm\s+(ls|list|view)|arduino-cli\s+board\s+list)\b",
    re.IGNORECASE,
)
SEGMENT_SPLIT = re.compile(r"&&|\|\||[;|\n]")
SKIP_PREFIX = re.compile(r"^(cd|set-location|export|set)\b|^\w+=\S*$", re.IGNORECASE)


def is_look_only(command: str | None) -> bool:
    """명령이 보기만 하는지. 하나라도 무언가를 실행·변경하면 False (cd 같은 이동은 무시)."""
    if not command:
        return True
    for seg in SEGMENT_SPLIT.split(command):
        seg = seg.strip().strip("()")
        if not seg or SKIP_PREFIX.match(seg):
            continue
        if LOOK_SUBCMDS.match(seg):
            continue
        if seg.split()[0].lower().split("/")[-1] not in LOOK_CMDS:
            return False
    return True


def classify(tool: str | None, command: str | None, edited: bool) -> int | None:
    """도구 하나가 가리키는 단계. 판단할 근거가 없으면 None(현재 단계 유지)."""
    if not tool:
        return None
    if tool in EDIT_TOOLS:
        return BUILD
    if tool in PLAN_TOOLS:
        return PLAN
    if tool in READ_TOOLS:
        return READ
    if tool in SHELL_TOOLS:
        if is_look_only(command):
            return READ  # ls, cat, git status … 보기만 하는 명령
        if edited and command and CHECK_RE.search(command):
            return REVIEW  # 수정한 뒤의 테스트·빌드
        # 스크립트 실행·업로드 등 실제 작업. 수정 전 테스트도 여기(검토로 건너뛰면 이후 수정 단계가 막힘)
        return BUILD
    return None  # Agent, MCP 도구 등: 단계 판단 보류


class ProgressTracker:
    def __init__(self, now: float, tau: float = 45.0):
        self.idx = READ
        self.since = now
        self.tau = tau
        self.edited = False
        self._floor = 0

    @property
    def phase(self) -> Phase:
        return PHASES[self.idx]

    def on_tool(self, tool: str | None, command: str | None, now: float) -> bool:
        """도구 사용을 반영. 단계가 올라가면 True."""
        target = classify(tool, command, self.edited)
        if tool in EDIT_TOOLS:
            self.edited = True
        if target is None or target <= self.idx:
            return False
        self._floor = self.percent(now)
        self.idx = target
        self.since = now
        return True

    def percent(self, now: float) -> int:
        p = self.phase
        t = max(0.0, now - self.since)
        v = p.lo + (p.hi - p.lo) * (1 - math.exp(-t / self.tau))
        return max(self._floor, int(v))
