# Lite 3 开发起点

从零建立的独立 Python 项目，使用 Python 3.10+ 标准库，无第三方运行依赖。

## 当前功能

- 生成基础 UDP 指令的离线报文预览。
- 校验 12 字节、小端序报文头及数据长度。
- 解析关节角度与关节角速度（各 12 个 double）。
- 被动接收指定机器人 IP 的 UDP 上报，默认监听 10 秒。
- 未知数据及整机状态 0x0901 保留原始内容；结构体对齐未核实前不解释电量等字段。

当前没有发送实机控制指令的入口，也没有连接过机器人。preview 仅显示报文，不能用来证明设备在线。

## 快速开始

在本项目目录运行：

```powershell
python -m unittest -v
python lite3.py preview heartbeat
python lite3.py decode "010004210000000000000000"
python lite3.py check-config
```

本机没有 python 命令时，可以用以下路径替换 python：

```powershell
& 'C:\Users\wansh\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' lite3.py preview heartbeat
```

## 连接配置

编辑 config.json：model 为实际版本，robot_ip 为运动主机 IP，listen_port 为机器人配置的上报目标端口。
IP 和上报端口故意留空，不能把控制端口当成上报端口。

command_port=43893 来自本地通信手册第 4 页，是运动主机接收控制命令的端口。
listen_ip=0.0.0.0 表示绑定本机所有网卡；可改成与机器人连接的本机网卡地址。
手册说明运动主机默认仅向感知主机上报，开发电脑接收数据可能需要调整机器人上的上报目标配置；本项目未做这些修改。

确认上报目标已指向开发电脑后，可运行：

```powershell
python lite3.py listen --seconds 10
```

没有收到报文时退出码为 2；这不直接说明机器人故障，应检查网络、上报地址、端口和防火墙。

## 协议依据

本地资料：D:\工作台\机器狗\4款小狗\开发手册

- Jueying Lite3 Motion Host Communication Interface(beta) V1.0.7-0.pdf：第 4–7 页报文和心跳，第 9–10 页基础指令，第 20–21 页关节上报及测试样本。
- Jueying Lite3 Motion Development Manual (beta) V2.0.1-0.pdf：第 11–13 页关节级 SDK 介绍。当前项目属于主机 UDP 通信工具，并非该关节级 SDK。
- Jueying Lite3 Perception Development Manual(beta) V2.1.1-0.pdf：已定位，尚未分析或实现感知接口。

通信手册注明适用于 jy_exe_87 (20230531)，尚未与实机固件核对。
心跳至少 2 Hz；移动模式轴指令至少 20 Hz。站起/趴下指令是切换指令，不能当成幂等的“站起”。软件急停与发送零速度是不同操作。

## 接下来

确认 Lite 3 版本、实机固件、运动主机 IP 和上报端口，先完成状态接收联调；再按具体功能需求增加控制接口。
