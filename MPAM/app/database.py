"""本地账户、工作簿快照和变更记录的 SQLite 存储。"""

from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile

from .excel_store import AssignError, ExcelStore, MonthKey, normalize_name, normalize_project_id, split_projects


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY COLLATE NOCASE,
    salt BLOB NOT NULL,
    password_hash BLOB NOT NULL,
    admin INTEGER NOT NULL CHECK (admin IN (0, 1)),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    must_change INTEGER NOT NULL DEFAULT 0 CHECK (must_change IN (0, 1))
);
CREATE TABLE IF NOT EXISTS workbooks (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL COLLATE NOCASE,
    name TEXT NOT NULL,
    digest TEXT NOT NULL,
    template BLOB NOT NULL,
    imported_at TEXT NOT NULL,
    UNIQUE (source, digest)
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS people (
    workbook INTEGER NOT NULL REFERENCES workbooks(id),
    name TEXT NOT NULL,
    ambiguous INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workbook, name)
);
CREATE TABLE IF NOT EXISTS months (
    workbook INTEGER NOT NULL REFERENCES workbooks(id),
    month INTEGER NOT NULL,
    PRIMARY KEY (workbook, month)
);
CREATE TABLE IF NOT EXISTS projects (
    workbook INTEGER NOT NULL REFERENCES workbooks(id),
    project TEXT NOT NULL,
    PRIMARY KEY (workbook, project)
);
CREATE TABLE IF NOT EXISTS assignments (
    workbook INTEGER NOT NULL,
    month INTEGER NOT NULL,
    person TEXT NOT NULL,
    project TEXT NOT NULL,
    PRIMARY KEY (workbook, month, person, project),
    FOREIGN KEY (workbook, month) REFERENCES months(workbook, month),
    FOREIGN KEY (workbook, person) REFERENCES people(workbook, name)
);
CREATE TABLE IF NOT EXISTS changes (
    id INTEGER PRIMARY KEY,
    workbook INTEGER NOT NULL REFERENCES workbooks(id),
    month INTEGER NOT NULL,
    person TEXT NOT NULL,
    action TEXT NOT NULL,
    previous TEXT NOT NULL,
    project TEXT NOT NULL,
    happened_at TEXT NOT NULL,
    operator TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS change_person_month ON changes(workbook, month, person, id);
"""


@dataclass(frozen=True)
class Account:
    username: str
    admin: bool
    enabled: bool
    must_change: bool


def data_directory() -> Path:
    override = os.environ.get("MPAM_DATA_DIR")
    if override:
        return Path(override)
    local = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    return local / "SkyOps" / "MPAM"


def timestamp() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def month_number(key: MonthKey) -> int:
    return key[0] * 100 + key[1]


def month_key(number: int) -> MonthKey:
    return divmod(number, 100)


def password_hash(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 600_000)


def new_secret(password: str) -> tuple[bytes, bytes]:
    salt = os.urandom(16)
    return salt, password_hash(password, salt)


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def write(self):
        with self.conn:
            self.conn.execute("BEGIN IMMEDIATE")
            yield self.conn

    def has_accounts(self) -> bool:
        return self.conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None

    @staticmethod
    def account(row) -> Account:
        return Account(row["username"], bool(row["admin"]), bool(row["enabled"]), bool(row["must_change"]))

    def authenticate(self, username: str, password: str) -> Account | None:
        row = self.conn.execute("SELECT * FROM users WHERE username=?", (normalize_name(username),)).fetchone()
        if row is None or not row["enabled"]:
            return None
        if hmac.compare_digest(password_hash(password, row["salt"]), row["password_hash"]):
            return self.account(row)
        return None

    def require_account(self, username: str, *, admin: bool = False) -> Account:
        row = self.conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if row is None or not row["enabled"] or row["must_change"] or (admin and not row["admin"]):
            raise AssignError("当前账号没有执行该操作的权限，请重新登录。")
        return self.account(row)

    def _create_user(self, username: str, password: str, *, admin: bool, must_change: bool) -> Account:
        username = normalize_name(username)
        if not username or len(username) > 40 or any(char.isspace() for char in username):
            raise AssignError("账号需为 1 至 40 个字符，且不能包含空白。")
        if self.conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            raise AssignError("该账号已经存在。")
        salt, secret = new_secret(password)
        self.conn.execute(
            "INSERT INTO users (username, salt, password_hash, admin, must_change) VALUES (?, ?, ?, ?, ?)",
            (username, salt, secret, admin, must_change),
        )
        return Account(username, admin, True, must_change)

    def create_admin(self, username: str, password: str) -> Account:
        with self.write():
            if self.has_accounts():
                raise AssignError("管理员已初始化，请返回后使用现有账号登录。")
            return self._create_user(username, password, admin=True, must_change=False)

    def users(self, actor: str) -> list[Account]:
        self.require_account(actor, admin=True)
        return [self.account(row) for row in self.conn.execute("SELECT * FROM users ORDER BY username")]

    def create_user(self, actor: str, username: str, password: str, *, admin: bool) -> None:
        with self.write():
            self.require_account(actor, admin=True)
            self._create_user(username, password, admin=admin, must_change=True)

    def _managed_username(self, actor: str, username: str) -> str:
        account = self.require_account(actor, admin=True)
        row = self.conn.execute("SELECT username FROM users WHERE username=?", (username,)).fetchone()
        if row is None:
            raise AssignError("该账号不存在。")
        if account.username == row[0]:
            raise AssignError("当前登录的管理员只能在账号菜单中修改自己的密码。")
        return row[0]

    def reset_password(self, actor: str, username: str, password: str) -> None:
        salt, secret = new_secret(password)
        with self.write():
            username = self._managed_username(actor, username)
            self.conn.execute(
                "UPDATE users SET salt=?, password_hash=?, must_change=1 WHERE username=?",
                (salt, secret, username),
            )

    def change_password(self, username: str, current: str, password: str) -> None:
        salt, secret = new_secret(password)
        with self.write():
            account = self.authenticate(username, current)
            if account is None:
                raise AssignError("当前密码不正确。")
            if current == password:
                raise AssignError("请选择一个不同的新密码。")
            self.conn.execute(
                "UPDATE users SET salt=?, password_hash=?, must_change=0 WHERE username=?",
                (salt, secret, account.username),
            )

    def set_user_enabled(self, actor: str, username: str, enabled: bool) -> None:
        with self.write():
            username = self._managed_username(actor, username)
            self.conn.execute("UPDATE users SET enabled=? WHERE username=?", (enabled, username))

    def set_user_role(self, actor: str, username: str, admin: bool) -> None:
        with self.write():
            username = self._managed_username(actor, username)
            self.conn.execute("UPDATE users SET admin=? WHERE username=?", (admin, username))


    def workbooks(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT id, name, source, imported_at FROM workbooks ORDER BY id DESC"
        ).fetchall()

    def active_workbook(self) -> int | None:
        row = self.conn.execute("SELECT value FROM settings WHERE key='active_workbook'").fetchone()
        return row["value"] if row else None

    def select_workbook(self, workbook: int) -> None:
        with self.write():
            self._select_workbook(workbook)

    def _select_workbook(self, workbook: int) -> None:
        self.conn.execute(
            "INSERT INTO settings VALUES ('active_workbook', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (workbook,),
        )

    def import_workbook(self, path: Path, actor: str) -> int:
        source = path.resolve()
        if source.suffix.lower() != ".xlsx":
            raise AssignError("请选择 .xlsx 格式的工作簿。")
        content = source.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        excel = ExcelStore(source).load(BytesIO(content))

        with self.write() as conn:
            self.require_account(actor)
            existing = conn.execute(
                "SELECT id FROM workbooks WHERE source=? AND digest=?", (str(source), digest),
            ).fetchone()
            if existing:
                workbook = existing["id"]
            else:
                workbook = conn.execute(
                    "INSERT INTO workbooks(source, name, digest, template, imported_at) VALUES (?, ?, ?, ?, ?)",
                    (str(source), source.name, digest, content, timestamp()),
                ).lastrowid
                conn.executemany("INSERT INTO people VALUES (?, ?, ?)", (
                    (workbook, person, person in excel.duplicate_people) for person in excel.people()
                ))
                conn.executemany("INSERT INTO months VALUES (?, ?)", (
                    (workbook, month_number(key)) for key in excel.month_keys()
                ))
                conn.executemany("INSERT INTO assignments VALUES (?, ?, ?, ?)", (
                    (workbook, month_number(key), person, project)
                    for key, person, project in excel.all_assignments()
                ))
                conn.executemany("INSERT INTO projects VALUES (?, ?)", (
                    (workbook, project) for project in excel.registered_projects()
                ))
                conn.executemany(
                    "INSERT INTO changes(workbook, month, person, action, previous, project, happened_at, operator) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    ((workbook, month_number(key), *fields) for key, *fields in excel.history_rows()),
                )
            self._select_workbook(workbook)
        return workbook


class AllocationStore:
    def __init__(self, database: Database, workbook: int, operator: str):
        self.database = database
        self.conn = database.conn
        self.workbook = workbook
        self.operator = operator
        row = self.conn.execute("SELECT source, name, template FROM workbooks WHERE id=?", (workbook,)).fetchone()
        if row is None:
            raise AssignError("找不到本地工作簿。")
        self.path = Path(row["source"])
        self.name = row["name"]
        self.project_color_map = ExcelStore(self.path).load(BytesIO(row["template"])).project_colors()

    def month_keys(self) -> list[MonthKey]:
        return [month_key(row[0]) for row in self.conn.execute(
            "SELECT month FROM months WHERE workbook=? ORDER BY month", (self.workbook,),
        )]

    def people(self) -> list[str]:
        return [row[0] for row in self.conn.execute(
            "SELECT name FROM people WHERE workbook=? ORDER BY rowid", (self.workbook,),
        )]

    @property
    def duplicate_people(self) -> list[str]:
        return [row[0] for row in self.conn.execute(
            "SELECT name FROM people WHERE workbook=? AND ambiguous=1", (self.workbook,),
        )]

    def projects_of(self, key: MonthKey, person: str) -> list[str]:
        return [row[0] for row in self.conn.execute(
            "SELECT project FROM assignments WHERE workbook=? AND month=? AND person=? ORDER BY rowid",
            (self.workbook, month_number(key), person),
        )]

    def who_has(self, key: MonthKey, project: str) -> list[str]:
        return [row[0] for row in self.conn.execute(
            "SELECT person FROM assignments WHERE workbook=? AND month=? AND project=? ORDER BY rowid",
            (self.workbook, month_number(key), project),
        )]

    def all_project_ids(self) -> list[str]:
        return [row[0] for row in self.conn.execute(
            "SELECT project FROM projects WHERE workbook=? "
            "UNION SELECT project FROM assignments WHERE workbook=? ORDER BY project",
            (self.workbook, self.workbook),
        )]

    def assigned_at(self, key: MonthKey, person: str) -> str:
        row = self.conn.execute(
            "SELECT action, happened_at FROM changes WHERE workbook=? AND month=? AND person=? ORDER BY id DESC LIMIT 1",
            (self.workbook, month_number(key), person),
        ).fetchone()
        return row["happened_at"] if row and row["action"] != "撤销" else ""

    @property
    def last_saved(self) -> str:
        row = self.conn.execute(
            "SELECT happened_at FROM changes WHERE workbook=? AND operator<>'' ORDER BY id DESC LIMIT 1",
            (self.workbook,),
        ).fetchone()
        return row[0] if row else ""

    def history(
        self,
        person: str = "",
        operator: str = "",
        key: MonthKey | None = None,
        project: str = "",
    ):
        rows = self.conn.execute(
            "SELECT month, person, action, previous, project, happened_at, operator FROM changes "
            "WHERE workbook=? AND instr(person, ?) > 0 AND instr(operator, ?) > 0 "
            "AND (? IS NULL OR month=?) "
            "AND (?='' OR instr(previous, ?) > 0 OR instr(project, ?) > 0) "
            "ORDER BY datetime(happened_at) DESC, id DESC",
            (
                self.workbook, person, operator,
                month_number(key) if key else None, month_number(key) if key else None,
                project, project, project,
            ),
        )
        return [(month_key(row[0]), *tuple(row)[1:]) for row in rows]


    @staticmethod
    def _project(value: str) -> str:
        project = normalize_project_id(value)
        if not project or len(project) > 40 or split_projects(project) != [project]:
            raise AssignError("项目号须为 1 至 40 个字符，且不能包含项目号分隔符。")
        return project

    def _person(self, value: str) -> str:
        name = normalize_name(value)
        if not name:
            raise AssignError("请输入姓名。")
        if name in self.duplicate_people:
            raise AssignError(f"工作簿中存在多行「{name}」，请先核对来源。")
        return name

    def _insert_person(self, name: str) -> None:
        self.conn.execute("INSERT INTO people(workbook, name) VALUES (?, ?)", (self.workbook, name))

    def add_person(self, value: str) -> str:
        with self.database.write():
            self.database.require_account(self.operator)
            person = self._person(value)
            if person in self.people():
                raise AssignError(f"「{person}」已经在人员列表中。")
            self._insert_person(person)
        return person

    def add_project(self, value: str) -> str:
        project = self._project(value)
        with self.database.write():
            self.database.require_account(self.operator)
            if project in self.all_project_ids():
                raise AssignError(f"项目号「{project}」已存在。")
            self.conn.execute("INSERT INTO projects VALUES (?, ?)", (self.workbook, project))
        return project

    def _record(self, key, person, action, previous, project):
        self.conn.execute(
            "INSERT INTO changes(workbook, month, person, action, previous, project, happened_at, operator) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (self.workbook, month_number(key), person, action, previous, project, timestamp(), self.operator),
        )

    def assign(self, key: MonthKey, person: str, value: str) -> str:
        if not 1900 <= key[0] <= 2200 or not 1 <= key[1] <= 12:
            raise AssignError("请选择有效的月份。")
        project = self._project(value)
        with self.database.write():
            self.database.require_account(self.operator)
            person = self._person(person)
            existing = self.projects_of(key, person)
            if existing:
                raise AssignError(f"该人员本月已有项目号「{existing[0]}」，每人每月只能分配一个，请使用修改。")
            if person not in self.people():
                self._insert_person(person)
            self.conn.execute("INSERT OR IGNORE INTO months VALUES (?, ?)", (self.workbook, month_number(key)))
            self.conn.execute(
                "INSERT INTO assignments VALUES (?, ?, ?, ?)", (self.workbook, month_number(key), person, project),
            )
            self._record(key, person, "分配", "", project)
        return project

    def replace_project(self, key: MonthKey, person: str, old_value: str, value: str) -> str:
        old = normalize_project_id(old_value)
        project = self._project(value)
        with self.database.write():
            self.database.require_account(self.operator)
            person = self._person(person)
            existing = self.projects_of(key, person)
            if old not in existing:
                raise AssignError("原项目号已变更，请刷新后重试。")
            if len(existing) > 1:
                raise AssignError("该人员本月有多个已有项目号，请先使用“整理”选择保留的一项。")
            if project in existing:
                raise AssignError(f"该人员本月已有「{project}」。")
            self.conn.execute(
                "UPDATE assignments SET project=? WHERE workbook=? AND month=? AND person=? AND project=?",
                (project, self.workbook, month_number(key), person, old),
            )
            self._record(key, person, "修改", old, project)
        return project

    def keep_single_project(self, key: MonthKey, person: str, keep_value: str) -> str:
        """把导入的多项目旧分配整理为一项，并逐条保留审计记录。"""
        keep = self._project(keep_value)
        with self.database.write():
            self.database.require_account(self.operator)
            person = self._person(person)
            existing = self.projects_of(key, person)
            if keep not in existing:
                raise AssignError("所选项目号已不存在，请刷新后重试。")
            if len(existing) <= 1:
                return keep
            for old in existing:
                if old == keep:
                    continue
                self.conn.execute(
                    "DELETE FROM assignments WHERE workbook=? AND month=? AND person=? AND project=?",
                    (self.workbook, month_number(key), person, old),
                )
                self._record(key, person, "整理", old, keep)
        return keep

    def export(self, target: Path) -> None:
        self.database.require_account(self.operator)
        target = target.resolve()
        if target.suffix.lower() != ".xlsx":
            raise AssignError("请将副本保存为 .xlsx 文件。")
        if target.exists() or self.conn.execute("SELECT 1 FROM workbooks WHERE source=?", (str(target),)).fetchone():
            raise AssignError("请选择一个新的文件名来保存 Excel 副本。")
        with self.conn:
            self.conn.execute("BEGIN")
            template = self.conn.execute("SELECT template FROM workbooks WHERE id=?", (self.workbook,)).fetchone()[0]
            months = self.month_keys()
            people = self.people()
            projects = {}
            for row in self.conn.execute(
                "SELECT month, person, project FROM assignments WHERE workbook=? ORDER BY rowid", (self.workbook,),
            ):
                projects.setdefault((month_key(row["month"]), row["person"]), []).append(row["project"])
        with NamedTemporaryFile(dir=target.parent, suffix=".xlsx", delete=False) as temporary:
            staged = Path(temporary.name)
        try:
            ExcelStore(target).load(BytesIO(template)).write_export(
                staged, months, people, lambda key, person: projects.get((key, person), []),
            )
            with target.open("xb"):
                pass
            try:
                os.replace(staged, target)
            except OSError:
                target.unlink(missing_ok=True)
                raise
        finally:
            staged.unlink(missing_ok=True)

