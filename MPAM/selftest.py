"""无界面自检：只验证 Excel 读写与判重规则，不弹窗口。

    python selftest.py

在临时目录里跑，不会碰 data/ 下的模拟表。
规则：同一人、同一月、同一个项目号只允许一次；不同项目号可继续添加。
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from excel_store import (  # noqa: E402
    AssignError,
    ExcelStore,
    join_projects,
    month_label,
    normalize_project_id,
    split_projects,
)
from openpyxl import Workbook  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

from mock_data import ensure_mock_workbook  # noqa: E402

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(("[OK]   " if condition else "[FAIL] ") + name + (f" — {detail}" if detail else ""))
    if not condition:
        failures.append(name)


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="mpam_"))
    book = ensure_mock_workbook(workdir / "月度项目分配-模拟.xlsx")
    store = ExcelStore(book).load()

    check("识别出 3 个月份列", len(store.month_keys()) == 3, str(store.month_keys()))
    check("识别出 4 个人名", len(store.people()) == 4, "、".join(store.people()))
    check(
        "张三 11 月已有两个项目号",
        store.projects_of((2026, 11), "张三") == ["12345", "67890"],
        str(store.projects_of((2026, 11), "张三")),
    )

    # 1) 同号重复分配必须被拒绝
    try:
        store.assign((2026, 11), "张三", "67890")
    except AssignError as error:
        check("同号重复分配被拒绝", True, str(error))
    else:
        check("同号重复分配被拒绝", False, "没有抛出异常")

    # 2) 拒绝后单元格不能被改写
    check(
        "拒绝后原值未被覆盖",
        store.projects_of((2026, 11), "张三") == ["12345", "67890"],
    )

    # 3) 同月分配不同项目号：允许
    try:
        written = store.assign((2026, 11), "张三", "99999")
        check("张三 11 月加第三个号成功", written == "99999")
        check(
            "张三 11 月现在是三个号",
            store.projects_of((2026, 11), "张三") == ["12345", "67890", "99999"],
        )
    except AssignError as error:
        check("张三 11 月加第三个号成功", False, str(error))

    # 4) 同号给不同的人：允许（软提示不拦截）
    try:
        store.assign((2026, 11), "赵六", "67890")
        check("赵六 11 月分配 67890 成功", True)
    except AssignError as error:
        check("赵六 11 月分配 67890 成功", False, str(error))

    # 5) 跨月是新周期
    try:
        store.assign((2026, 12), "张三", "67890")
        check("张三 12 月分配 67890 成功", True)
    except AssignError as error:
        check("张三 12 月分配 67890 成功", False, str(error))

    # 6) 未来月份自动建列（表里原本没有 2027-01）
    try:
        store.assign((2027, 1), "李四", "11111")
        check("2027年1月 自动建列并写入", store.projects_of((2027, 1), "李四") == ["11111"])
        check("月份列总数变为 4", len(store.month_keys()) == 4, str(store.month_keys()))
    except AssignError as error:
        check("2027年1月 自动建列并写入", False, str(error))

    # 7) 落盘后重新加载数据仍在
    reloaded = ExcelStore(book).load()
    check(
        "重新载入后张三 11 月仍是三个号",
        reloaded.projects_of((2026, 11), "张三") == ["12345", "67890", "99999"],
    )
    check("重新载入后 2027年1月 李四仍在", reloaded.projects_of((2027, 1), "李四") == ["11111"])
    check("明细表记录了新分配", bool(reloaded.assigned_at((2027, 1), "李四")))

    # 8) 反查：67890 命中 张三11月、赵六11月、张三12月
    hits = reloaded.lookup("67890")
    check("反查 67890 命中三条", len(hits) == 3, str(hits))

    # 9) 修改项目号（把 12345 改成 77777）
    try:
        changed = reloaded.replace_project((2026, 11), "张三", "12345", "77777")
        check("修改项目号成功", changed == "77777")
        check(
            "修改后列表正确",
            reloaded.projects_of((2026, 11), "张三") == ["77777", "67890", "99999"],
            str(reloaded.projects_of((2026, 11), "张三")),
        )
    except AssignError as error:
        check("修改项目号成功", False, str(error))

    # 10) 改成已存在的项目号必须被拒绝
    try:
        reloaded.replace_project((2026, 11), "张三", "77777", "67890")
    except AssignError as error:
        check("改成已存在的号被拒绝", True, str(error))
    else:
        check("改成已存在的号被拒绝", False, "没有抛出异常")

    # 11) 改一个不存在的原号必须被拒绝
    try:
        reloaded.replace_project((2026, 11), "张三", "88888", "123")
    except AssignError as error:
        check("改不存在的原号被拒绝", True, str(error))
    else:
        check("改不存在的原号被拒绝", False, "没有抛出异常")

    # 12) 重新载入：修改已落盘 + 明细留痕
    again = ExcelStore(book).load()
    check(
        "重新载入后修改已生效",
        again.projects_of((2026, 11), "张三") == ["77777", "67890", "99999"],
    )
    found_modify = False
    for row in again._detail.iter_rows(min_row=2, values_only=True):
        if (
            row
            and len(row) > 4
            and str(row[3]) == "修改"
            and str(row[2]) == "77777"
            and str(row[4]) == "12345"
        ):
            found_modify = True
    check("明细记录了修改（12345 → 77777）", found_modify)

    # 13) 高亮：67890 在 2026-11 出现两次（张三、赵六）→ 两格标黄，李四不标
    col_nov = again._columns[(2026, 11)]
    cell_zs = again._summary.cell(row=again._rows["张三"], column=col_nov)
    cell_zl = again._summary.cell(row=again._rows["赵六"], column=col_nov)
    cell_ls = again._summary.cell(row=again._rows["李四"], column=col_nov)
    check("张三 11 月被高亮", ExcelStore._is_highlighted(cell_zs))
    check("赵六 11 月被高亮", ExcelStore._is_highlighted(cell_zl))
    check("李四 11 月未被高亮", not ExcelStore._is_highlighted(cell_ls))

    # 14) 自适应列宽：月份列宽度已写回文件
    width = again._summary.column_dimensions[get_column_letter(col_nov)].width
    check("月份列宽自适应（>8）", bool(width) and width > 8, str(width))

    # 15) 检索：按人员 / 按项目号（一字不差）
    by_person = again.search_by_person("张三")
    check("按人员检索有结果", len(by_person) >= 3, str(len(by_person)))
    check(
        "按人员检索覆盖所有月份",
        any(key == (2026, 11) for key, *_ in by_person)
        and any(key == (2026, 12) for key, *_ in by_person),
    )
    by_project = again.search_by_project("67890")
    check("按项目号检索有结果", len(by_project) >= 2, str(len(by_project)))
    check("按项目号一字不差（前缀查不到）", again.search_by_project("6789") == [])
    check("按项目号检索出人员", {name for _, name, _, _ in by_project} >= {"张三", "赵六"})

    # 15b) 下拉候选 + 人员模糊检索
    ids = again.all_project_ids()
    check("项目号清单去重排序", ids == sorted(set(ids)) and len(ids) >= 3, str(ids))
    check("项目号清单包含已知号", {"67890", "99999", "77777"} <= set(ids), str(ids))
    fuzzy = again.search_people("张")
    check("模糊检索（包含）命中张三", {name for _, name, _, _ in fuzzy} == {"张三"})
    check("模糊检索覆盖张三全部月份", len(fuzzy) >= 3, str(len(fuzzy)))
    check("模糊检索精确全名", len(again.search_people("张三")) == len(fuzzy))
    check("模糊检索空文本返回空", again.search_people("") == [])
    check("模糊检索无匹配返回空", again.search_people("不存在的人") == [])

    # 16) 导入兼容：表名不叫「分配汇总」、表头不在第 1 行
    other = workdir / "带标题行的表.xlsx"
    book2 = Workbook()
    sheet2 = book2.active
    sheet2.title = "其他表名"
    sheet2["A1"] = "2026 年度项目分配表"
    sheet2["A2"] = "人员"
    sheet2["B2"] = "2026年1月"
    sheet2["C2"] = "2026年2月"
    sheet2["A3"] = "王五"
    sheet2["B3"] = "A001"
    sheet2["A4"] = "赵六"
    book2.save(other)

    imported = ExcelStore(other).load()
    check("自动识别表头行（第 2 行）", imported._header_row == 2, str(imported._header_row))
    check("导入后识别月份", imported.month_keys() == [(2026, 1), (2026, 2)], str(imported.month_keys()))
    check("导入后识别人员", imported.people() == ["王五", "赵六"], str(imported.people()))
    check("导入后读到项目号", imported.projects_of((2026, 1), "王五") == ["A001"])

    # 17) 新增人员：写到 A 列第一个空行
    added = imported.add_person("钱七")
    check("新增人员成功", added == "钱七")
    check("人员列表已更新", "钱七" in imported.people(), str(imported.people()))
    check("写到了第 5 行空行", imported._rows.get("钱七") == 5, str(imported._rows.get("钱七")))
    reread = ExcelStore(other).load()
    check("重新载入后新人员在表里", "钱七" in reread.people(), str(reread.people()))

    # 17b) 项目号台账：新增 + 去重 + 持久化
    pid_added = imported.add_project("XJ-999")
    check("新增项目号成功", pid_added == "XJ-999")
    check("项目号进入候选", "XJ-999" in imported.all_project_ids(), str(imported.all_project_ids()))
    try:
        imported.add_project("XJ-999")
    except AssignError:
        check("重复项目号被拒绝", True)
    else:
        check("重复项目号被拒绝", False, "没有抛出异常")
    reread3 = ExcelStore(other).load()
    check("重新载入后项目号仍在", "XJ-999" in reread3.all_project_ids(), str(reread3.all_project_ids()))

    # 18) 拆分/合并回环
    check(
        "拆分合并回环",
        split_projects(join_projects(["12345", "67890", "0010001"])) == ["12345", "67890", "0010001"],
    )
    check(
        "全角/空格归一化",
        normalize_project_id("　００１０００１ ") == "0010001",
        normalize_project_id("　００１０００１ "),
    )
    check("月份标签", month_label((2026, 11)) == "2026年11月")

    print()
    if failures:
        print(f"自检未通过：{len(failures)} 项 — {'、'.join(failures)}")
        return 1
    print("自检通过：同月多项目、同号拦截、修改、高亮、自适应列宽、检索、导入识别、新增人员、落盘都正常。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
