# STK 全球覆盖通信时长仿真工程

基于 MATLAB/Python 与 STK 12.6 Object Model 的全球通信覆盖时长仿真工程。

- `MATLAB/`：已验证 MATLAB 参考实现；
- `Python/`：当前维护和发布的 Python 3.10 桌面程序。

Python 版本支持 CelesTrak 在线 TLE、按电脑日期自动设置 24 小时场景、三星几何星间中继、五个文档站址、带单位的站址参数、可调最低仰角、可选太阳干扰规避、1 小时时长梯度，以及按需计算任意新增站的覆盖时长增益。

安装、运行、代码结构和 EXE 打包说明见 [`Python/README.md`](Python/README.md) 与 [`Python/docs/PROJECT_GUIDE.md`](Python/docs/PROJECT_GUIDE.md)。
