from stk_api.core import STKCore


def connect_stk():
    """优先连接已打开的 STK 12，否则新建实例。"""
    _app, root = STKCore.start_stk("auto")
    print("STK Root 对象获取成功：", root)
    return root


if __name__ == "__main__":
    stk_root = connect_stk()
