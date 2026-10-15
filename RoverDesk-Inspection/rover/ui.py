import ipaddress,json,time
from pathlib import Path
from urllib.parse import urlparse
from PySide6.QtCore import Qt,QTimer,QEvent,QSize
from PySide6.QtGui import QPixmap,QColor,QShortcut,QKeySequence,QIcon,QPainter,QPen,QPainterPath
from PySide6.QtWidgets import *
from .model import FIELDS,JOINTS,display
from .motion import MotionError,MotionController
from .text_commands import COMMANDS,parse_command
from .alarms import AlarmMonitor,AlarmAudio
from .inspection_ui import InspectionPanel
STYLE="""
*{font-family:'Microsoft YaHei','Segoe UI';font-size:13px;}QMainWindow,QDialog{background:#0c121b;}QWidget{color:#dfe8f3;}
QFrame#side{background:#111b28;border-right:1px solid #273345;}QFrame#panel{background:#141f2e;border:1px solid #29364a;border-radius:12px;}
QLabel#muted{color:#91a4bb;font-size:12px;}QLabel#title{font-size:26px;font-weight:700;}QLabel#brand{color:#63e4cd;font-size:22px;font-weight:800;}
QLabel#value{font-size:29px;font-weight:700;}QLabel#video{background:#080d14;border:1px solid #253447;border-radius:10px;color:#8498b1;}
QLabel#pill{background:#20363b;color:#70e6d0;border-radius:7px;padding:7px;}
QPushButton{background:#25354b;border:1px solid #354962;border-radius:7px;padding:8px 13px;}QPushButton:hover{background:#314761;}
QPushButton#primary{background:#55ddc4;color:#0b2424;border:none;font-weight:bold;}QPushButton:disabled{background:#182230;color:#526277;border-color:#263244;}
QComboBox,QLineEdit{background:#0c1521;border:1px solid #344660;padding:8px;border-radius:6px;}QComboBox QAbstractItemView{background:#182536;}
QTabWidget::pane{border:none;}QTabBar::tab{color:#91a4bb;padding:11px 18px;border-bottom:2px solid transparent;}QTabBar::tab:selected{color:#67e4ce;border-bottom:2px solid #67e4ce;}
QTableWidget{background:#121d2b;alternate-background-color:#162333;border:1px solid #27364a;gridline-color:#223146;selection-background-color:#274754;}
QHeaderView::section{background:#1e2c3e;color:#99aec8;border:none;padding:9px;}QTextEdit{background:#111c2a;border:1px solid #293b52;border-radius:8px;padding:10px;}
QScrollBar:vertical{background:#101925;width:10px;}QScrollBar::handle:vertical{background:#364b63;min-height:28px;border-radius:5px;}
"""
STATUS={'live':'实时','inferred':'日志推断','stale':'已过期','unavailable':'未收到','unsupported':'不支持'}
def label(text,kind=None):
    w=QLabel(text)
    if kind:w.setObjectName(kind)
    return w
def table(headers):
    t=QTableWidget(0,len(headers));t.setHorizontalHeaderLabels(headers);t.setAlternatingRowColors(True);t.setEditTriggers(QTableWidget.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectRows);t.verticalHeader().hide();t.verticalHeader().setDefaultSectionSize(29)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);t.horizontalHeader().setStretchLastSection(True);return t
def cell(t,r,c,text,color='#dfe8f3'):
    item=t.item(r,c)
    if item is None:item=QTableWidgetItem();t.setItem(r,c,item)
    item.setText(str(text));item.setForeground(QColor(color))
def panel(title):
    box=QFrame();box.setObjectName('panel');lay=QVBoxLayout(box);lay.setContentsMargins(17,14,17,14);lay.addWidget(label(title));return box,lay
def button(text,fn,primary=False):
    b=QPushButton(text);b.clicked.connect(fn)
    if primary:b.setObjectName('primary')
    return b

def direction_icon(direction):
    pixmap=QPixmap(32,32);pixmap.fill(Qt.transparent)
    painter=QPainter(pixmap);painter.setRenderHint(QPainter.Antialiasing)
    pen=QPen(QColor('#dfe8f3'),2.7);pen.setCapStyle(Qt.RoundCap);pen.setJoinStyle(Qt.RoundJoin);painter.setPen(pen)
    if direction.startswith('turn_'):
        if direction=='turn_left':painter.translate(32,0);painter.scale(-1,1)
        path=QPainterPath();path.moveTo(7,26);path.lineTo(7,16);path.cubicTo(7,4,25,4,25,16)
        painter.drawPath(path);painter.drawLine(25,16,19,10);painter.drawLine(25,16,30,10)
    else:
        painter.translate(16,16);painter.rotate({'forward':0,'backward':180,'left':-90,'right':90}[direction])
        painter.drawLine(0,11,0,-11);painter.drawLine(0,-11,-7,-4);painter.drawLine(0,-11,7,-4)
    painter.end();return QIcon(pixmap)

class ProfileDialog(QDialog):
    def __init__(self,profile,parent):
        super().__init__(parent);self.setWindowTitle('机器狗连接配置');self.resize(510,430);form=QFormLayout(self);self.edits={}
        for key,name in [('name','设备名称'),('robot_ip','运动主机 IP'),('listen_ip','本机发送 IP（接收监听所有地址）'),('listen_port','UDP 接收端口'),('ssh_user','SSH 用户名'),('camera_url','摄像头 RTSP 地址')]:
            w=QLineEdit(str(profile[key]));self.edits[key]=w;form.addRow(name,w)
        form.addRow(label('适配器：Lite 3 · 仅保存电脑端配置，不修改机器人。','muted'))
        b=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);b.accepted.connect(self.accept);b.rejected.connect(self.reject);form.addRow(b)
    def accept(self):
        try:
            d={k:w.text().strip() for k,w in self.edits.items()};ipaddress.IPv4Address(d['robot_ip']);ipaddress.IPv4Address(d['listen_ip']);d['listen_port']=int(d['listen_port'])
            if not 1<=d['listen_port']<=65535:raise ValueError('端口应为 1–65535')
            u=urlparse(d['camera_url'])
            if u.scheme!='rtsp' or not u.hostname or u.username or u.password:raise ValueError('请输入不含账号密码的 RTSP 地址')
            if not d['name'] or not d['ssh_user']:raise ValueError('设备名和用户名不能为空')
            self.result_profile={**d,'adapter':'lite3'}
        except ValueError as e:QMessageBox.warning(self,'配置有误',str(e));return
        super().accept()

class MainWindow(QMainWindow):
    def __init__(self,runtime,bridge,data_dir,profiles):
        super().__init__();self.runtime=runtime;self.bridge=bridge;self.data_dir=Path(data_dir);self.profiles=profiles
        self.hold_button=None;self.hold_direction=None;self.last_frame=0;self.pixmap=None;self.setWindowTitle('Rover Desk · 机器狗工作台');self.resize(1460,940);self.setMinimumSize(1120,850);self.setStyleSheet(STYLE)
        base=QWidget();self.setCentralWidget(base);row=QHBoxLayout(base);row.setContentsMargins(0,0,0,0);row.setSpacing(0)
        side=QFrame();side.setObjectName('side');side.setFixedWidth(225);sl=QVBoxLayout(side);sl.setContentsMargins(19,27,19,23);sl.setSpacing(13)
        sl.addWidget(label('ROVER DESK','brand'));sl.addWidget(label('机器狗工作台  /  0.3.0 巡检版','muted'));sl.addSpacing(22);sl.addWidget(label('设备连接','muted'))
        self.select=QComboBox();self.select.addItems([p['name'] for p in profiles]);sl.addWidget(self.select);self.hostlabel=label(profiles[0]['robot_ip'],'muted');sl.addWidget(self.hostlabel)
        sl.addWidget(button('编辑连接',self.edit_profile));sl.addWidget(button('＋ 添加设备配置',self.add_profile));sl.addSpacing(10);sl.addWidget(label('SSH 密码 · 仅本次会话','muted'))
        self.password=QLineEdit();self.password.setEchoMode(QLineEdit.Password);self.password.setPlaceholderText('请输入密码');sl.addWidget(self.password)
        self.ssh_input_state=None
        self.show_password=QCheckBox('显示密码');self.show_password.setAccessibleName('显示 SSH 密码');self.show_password.toggled.connect(lambda visible:self.password.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password));sl.addWidget(self.show_password)
        sl.addWidget(button('连接设备',self.connect_robot,True));sl.addWidget(button('断开连接',self.disconnect_robot));sl.addSpacing(14);self.links={}
        for name in ('UDP','SSH','摄像头'):
            w=label(name+' · 未连接','muted');w.setWordWrap(True);self.links[name]=w;sl.addWidget(w)
        sl.addStretch();sl.addWidget(label('DESKTOP CONTROL','pill'));note=label('桌面遥控默认锁定。\nAI / MCP 保持只读。','muted');note.setWordWrap(True);sl.addWidget(note);row.addWidget(side)
        content=QWidget();cl=QVBoxLayout(content);cl.setContentsMargins(27,22,27,16);cl.setSpacing(13);row.addWidget(content,1)
        top=QHBoxLayout();titles=QVBoxLayout();titles.addWidget(label('机器人状态中心','title'));self.subtitle=label('连接机器狗，查看实时状态与摄像头','muted');titles.addWidget(self.subtitle);top.addLayout(titles);top.addStretch()
        self.coverage=label('等待连接','pill');top.addWidget(self.coverage);cl.addLayout(top)
        self.notice=label('遥控默认关闭 · 启用后按住移动、松开停止；不会修改机器人的持久配置。','muted');self.notice.setWordWrap(True);cl.addWidget(self.notice)
        self.alarm_monitor=AlarmMonitor();self.alarm_audio=AlarmAudio()
        self.tabs=QTabWidget();cl.addWidget(self.tabs,1);self.make_overview();self.make_text_commands();self.make_alarms();self.make_fields();self.make_joints();self.make_diagnostics();self.make_mcp()
        self.inspection_panel=InspectionPanel(runtime,self.data_dir,self);self.tabs.addTab(self.inspection_panel,'房间巡检')
        cl.addWidget(label('LOCAL WORKSPACE     •     状态 / 视频 / AI 只读接入','muted'))
        self.select.currentIndexChanged.connect(lambda:self.hostlabel.setText(self.profiles[self.select.currentIndex()]['robot_ip']))
        self.timer=QTimer(self);self.timer.timeout.connect(self.refresh);self.timer.start(250)
        self.hold_timer=QTimer(self);self.hold_timer.timeout.connect(self.renew_motion);self.hold_timer.start(40)
        QApplication.instance().installEventFilter(self)
        self.stop_shortcut=QShortcut(QKeySequence('Escape'),self);self.stop_shortcut.activated.connect(self.stop_motion)
    def make_overview(self):
        page=QWidget();outer=QGridLayout(page);outer.setContentsMargins(0,10,0,0);outer.setHorizontalSpacing(15);outer.setVerticalSpacing(14);outer.setColumnStretch(0,3);outer.setColumnStretch(1,2);outer.setRowStretch(0,3);outer.setRowStretch(1,2)
        cam,lay=panel('摄像头 / LIVE VIEW');self.video=label('连接后显示摄像头画面','video');self.video.setAlignment(Qt.AlignCenter);self.video.setMinimumSize(450,290);lay.addWidget(self.video,1)
        cb=QHBoxLayout();self.camera_info=label('尚未连接','muted');cb.addWidget(self.camera_info,1);cb.addWidget(button('保存当前画面',self.save_frame));lay.addLayout(cb);outer.addWidget(cam,0,0)
        metrics=QWidget();grid=QGridLayout(metrics);grid.setContentsMargins(0,0,0,0);grid.setSpacing(12);self.cards={}
        for i,(key,title) in enumerate([('battery.percent','电池电量'),('basic','基本状态'),('battery.voltage','电池电压'),('battery.temperature','电池温度')]):
            box,lay=panel(title);v=label('—','value');v.setWordWrap(True);lay.addWidget(v,1);s=label('未收到','muted');s.setWordWrap(True);lay.addWidget(s);self.cards[key]=(v,s);grid.addWidget(box,i//2,i%2)
        outer.addWidget(metrics,0,1);box,lay=panel('运动与感知状态')
        self.quick=table(['数据','值','质量']);self.quick_keys=['gait','motion','rpy.roll','rpy.pitch','rpy.yaw','ultrasound.front','ultrasound.rear','balance','zero','log.motion_hint'];self.quick.setRowCount(len(self.quick_keys));lay.addWidget(self.quick);outer.addWidget(box,1,1)
        box,lay=panel('运动遥控 / 慢速步态');controls=QHBoxLayout()
        self.arm_box=QCheckBox('启用遥控');self.arm_box.toggled.connect(self.toggle_motion);controls.addWidget(self.arm_box)
        self.pose_choice=QComboBox();self.pose_choice.addItems(['现场姿态：未确认','现场确认：已趴下','现场确认：已站立']);self.pose_choice.currentIndexChanged.connect(self.confirm_pose);controls.addWidget(self.pose_choice,1);self.pose_choice.hide();self.pose_auto=label('姿态：等待实时状态','muted');self.pose_auto.setWordWrap(True);controls.addWidget(self.pose_auto,1);lay.addLayout(controls)
        self.motion_status=label('遥控未启用','muted');self.motion_status.setWordWrap(True);lay.addWidget(self.motion_status)
        speed_row=QHBoxLayout();self.speed_text=label('速度档位：1 / 5','muted');speed_row.addWidget(self.speed_text)
        self.speed_slider=QSlider(Qt.Horizontal);self.speed_slider.setRange(1,5);self.speed_slider.setValue(1);self.speed_slider.setTickPosition(QSlider.TicksBelow);self.speed_slider.setTickInterval(1);self.speed_slider.setEnabled(False)
        self.speed_slider.setToolTip('低 → 高；调节移动和转弯的控制强度，不代表固定米/秒。先松开方向键再换档；重新连接恢复 1 档。')
        self.speed_slider.valueChanged.connect(self.change_speed);speed_row.addWidget(self.speed_slider,1);lay.addLayout(speed_row)
        self.motion_tabs=QTabWidget();self.motion_tabs.setMinimumHeight(124);self.motion_tabs.setObjectName('motionControlTabs')
        text_page=QWidget();g=QGridLayout(text_page);g.setContentsMargins(0,5,0,5);g.setSpacing(5);self.motion_buttons={}
        for text,key,r,c in [('左转','turn_left',0,0),('前进','forward',0,1),('右转','turn_right',0,2),('左横移','left',1,0),('后退','backward',1,1),('右横移','right',1,2)]:
            b=QPushButton(text);b.setFocusPolicy(Qt.NoFocus);b.setEnabled(False);b.pressed.connect(lambda k=key,w=b:self.begin_motion(k,w));b.released.connect(self.stop_motion);g.addWidget(b,r,c);self.motion_buttons[key]=b
        self.motion_tabs.addTab(text_page,'文字按钮')
        icon_page=QWidget();icon_page.setMinimumHeight(83);icons=QGridLayout(icon_page);icons.setContentsMargins(0,5,0,5);icons.setSpacing(5);self.icon_motion_buttons={}
        for glyph,key,name,r,c in [('↶','turn_left','左转',0,0),('↑','forward','前进',0,1),('↷','turn_right','右转',0,2),('←','left','左横移',1,0),('→','right','右横移',1,2),('↓','backward','后退',1,1)]:
            b=QPushButton();b.setIcon(direction_icon(key));b.setIconSize(QSize(26,26));b.setFocusPolicy(Qt.NoFocus);b.setEnabled(False);b.setMinimumHeight(34)
            b.setAccessibleName(name);b.setToolTip(name+'：按住移动，松开停止');b.setStyleSheet('padding:2px 10px;')
            b.pressed.connect(lambda k=key,w=b:self.begin_motion(k,w));b.released.connect(self.stop_motion)
            icons.addWidget(b,r,c);self.icon_motion_buttons[key]=b
        self.motion_tabs.addTab(icon_page,'方向图标');self.motion_tabs.currentChanged.connect(self.change_motion_tab);lay.addWidget(self.motion_tabs)
        posture_row=QHBoxLayout()
        for text,target in [('起立','stand'),('趴下','sit')]:
            b=button(text,lambda checked=False,t=target:self.posture_motion(t));posture_row.addWidget(b);self.motion_buttons[target]=b
            if target=='stand':posture_row.addWidget(button('停止 / Esc',self.stop_motion))
        lay.addLayout(posture_row)
        self.estop_button=button('软件急停',self.emergency_motion);self.estop_button.setStyleSheet('background:#782e38;color:white;font-weight:bold;');lay.addWidget(self.estop_button)
        info=label('按住移动，松开归零；失焦锁定。软件急停不能替代实体急停。','muted');info.setWordWrap(True);lay.addWidget(info);outer.addWidget(box,1,0);self.tabs.addTab(page,'总览')
    def make_text_commands(self):
        page=QWidget();lay=QVBoxLayout(page);lay.setSpacing(16)
        lay.addWidget(label('文字 / 语音指令','title'))
        note=label('先在总览中启用遥控并确认姿态，再输入单条口令。点击下方口令可填入文本框。','muted');note.setWordWrap(True);lay.addWidget(note)
        row=QHBoxLayout();self.command_input=QLineEdit();self.command_input.setPlaceholderText('输入指令，例如：起立、向左看、打招呼');self.command_input.setMaxLength(80);row.addWidget(self.command_input,1)
        self.microphone_button=QPushButton('麦克风（预留）');self.microphone_button.setEnabled(False);self.microphone_button.setToolTip('后续接入 AI 语音识别，将识别文本填入左侧输入框');row.addWidget(self.microphone_button)
        self.command_execute=button('执行指令',self.execute_text_command,True);row.addWidget(self.command_execute);lay.addLayout(row)
        self.command_result=label('尚未执行；填入文字不会触发动作','muted');self.command_result.setWordWrap(True);lay.addWidget(self.command_result)
        grid=QGridLayout()
        for i,name in enumerate(COMMANDS):
            grid.addWidget(button(name,lambda checked=False,n=name:self.set_command_text(n)),i//5,i%5)
        lay.addLayout(grid)
        info=label('前进、后退、横移：1 秒后停止。起立／趴下及打招呼按明确状态确认完成；其余动作需观察，15 秒仍未确认则停止并锁定。\n失焦停止移动并锁定输入，离散动作继续受监测；已接管会话保持心跳，断开设备后结束。\n原厂文字动作不使用手动速度档位。“已发送”不等于完成；麦克风尚未接入。','muted');info.setWordWrap(True);lay.addWidget(info)
        row=QHBoxLayout();self.command_stop=button('停止 / Esc',self.stop_text_command);self.command_estop=button('软件急停',self.emergency_motion);row.addWidget(self.command_stop);row.addWidget(self.command_estop);lay.addLayout(row);lay.addStretch();self.tabs.addTab(page,'文字 / 语音')
    def set_command_text(self,text):
        self.command_input.setText(text)
    def execute_text_command(self):
        try:name,value=parse_command(self.command_input.text())
        except ValueError as e:self.command_result.setText(str(e));return
        c=self.runtime.motion
        if c is None:self.command_result.setText('请先连接设备');return
        self.hold_button=None;self.hold_direction=None
        if self.motion_call(lambda controller:controller.text_command(value)):
            self.command_result.setText('已发送：'+name+'；请观察实际结果')
        else:self.command_result.setText('未执行：'+c.message)
    def stop_text_command(self):
        if self.runtime.motion:
            self.hold_button=None;self.hold_direction=None
            if self.motion_call(lambda c:c.text_command(7)):self.command_result.setText('已发送停止口令')
    def motion_call(self,fn):
        c=self.runtime.motion
        if c is None:return False
        try:fn(c);return True
        except (MotionError,OSError) as e:
            self.hold_button=None;self.hold_direction=None
            if isinstance(e,OSError):
                try:c.disarm('通信失败，遥控已锁定')
                except OSError:pass
            c.message=str(e);self.motion_status.setText(str(e));return False
    def change_speed(self,level):
        self.motion_call(lambda c:c.set_speed(level))
        actual=self.runtime.motion.status()['speed_level'] if self.runtime.motion else 1
        self.speed_slider.blockSignals(True);self.speed_slider.setValue(actual);self.speed_slider.blockSignals(False)
        self.speed_text.setText(f'速度档位：{actual} / 5')
    def toggle_motion(self,enabled):
        if enabled:
            ok=self.motion_call(lambda c:c.arm())
            if not ok:
                self.arm_box.blockSignals(True);self.arm_box.setChecked(False);self.arm_box.blockSignals(False)
        else:self.lock_motion('遥控已关闭')
    def confirm_pose(self,index):
        if not self.runtime.motion:return
        pose={0:None,1:'sit',2:'stand'}[index]
        if not self.motion_call(lambda c:c.confirm_posture(pose)):
            self.pose_choice.blockSignals(True);self.pose_choice.setCurrentIndex(0);self.pose_choice.blockSignals(False)
    def begin_motion(self,direction,widget):
        if self.motion_call(lambda c:c.begin(direction)):self.hold_button=widget;self.hold_direction=direction
    def change_motion_tab(self,index):
        if self.hold_button is not None:
            self.hold_button.setDown(False)
            self.stop_motion()
    def renew_motion(self):
        if not self.hold_button:return
        if not self.isActiveWindow() or not self.hold_button.isDown():
            self.stop_motion();return
        self.motion_call(lambda c:c.renew(self.hold_direction))
    def stop_motion(self):
        self.hold_button=None;self.hold_direction=None
        self.motion_call(lambda c:c.stop())
    def lock_motion(self,reason,focus_only=False):
        self.hold_button=None;self.hold_direction=None
        self.motion_call(lambda c:c.lock_input(reason) if focus_only else c.disarm(reason))
        if hasattr(self,'arm_box'):
            self.arm_box.blockSignals(True);self.arm_box.setChecked(False);self.arm_box.blockSignals(False)
            self.pose_choice.blockSignals(True);self.pose_choice.setCurrentIndex(0);self.pose_choice.blockSignals(False)
    def posture_motion(self,target):
        self.hold_button=None;self.hold_direction=None
        self.motion_call(lambda c:c.posture(target))
    def emergency_motion(self):
        self.hold_button=None;self.hold_direction=None
        self.motion_call(lambda c:c.emergency_stop())
    def eventFilter(self,obj,event):
        if event.type()==QEvent.ApplicationDeactivate or (obj is self and event.type()==QEvent.WindowDeactivate and not QApplication.activePopupWidget() and not QApplication.activeModalWidget()):
            if hasattr(self,'arm_box'):self.lock_motion('窗口失焦，遥控已锁定',focus_only=True)
        return super().eventFilter(obj,event)
    def make_alarms(self):
        page=QWidget();lay=QVBoxLayout(page);lay.setSpacing(12)
        row=QHBoxLayout();self.alarm_summary=label('未连接 · 等待告警数据','title');row.addWidget(self.alarm_summary,1)
        self.alarm_sound=QCheckBox('开启告警声音');self.alarm_sound.setChecked(True);self.alarm_sound.toggled.connect(self.set_alarm_sound);row.addWidget(self.alarm_sound);lay.addLayout(row)
        self.alarm_audio_status=label('紧急：滴滴，停顿 3 秒；一般：嘟嘟，停顿 5 秒。紧急告警优先播放。','muted');self.alarm_audio_status.setWordWrap(True);lay.addWidget(self.alarm_audio_status)
        self.alarm_table=table(['级别','告警项目','当前状态','依据 / 条件']);lay.addWidget(self.alarm_table,2)
        info=label('未判定不代表正常。过温、过流、跌倒及原厂 App 断连暂缺明确上报源。通信类告警连接后等待 10 秒开始检测；手动断开会停止声音。','muted');info.setWordWrap(True);lay.addWidget(info)
        lay.addWidget(label('本次运行告警记录（最近 300 条）','muted'));self.alarm_history=table(['时间','级别','项目','变化','依据']);lay.addWidget(self.alarm_history,1)
        self.alarm_tab_index=self.tabs.addTab(page,'告警')
    def set_alarm_sound(self,enabled):
        self.alarm_audio.enabled=enabled
        if not enabled:self.alarm_audio.stop()
    def refresh_alarms(self,snapshot,stamp):
        rows=self.alarm_monitor.evaluate(snapshot,self.runtime.adapter is not None,stamp)
        urgent=sum(r[1]=='紧急' and r[3]=='告警中' for r in rows);general=sum(r[1]=='一般' and r[3]=='告警中' for r in rows)
        self.alarm_summary.setText(f'紧急 {urgent} 项 · 一般 {general} 项' if self.runtime.adapter else '未连接 · 等待告警数据')
        self.tabs.setTabText(self.alarm_tab_index,f'告警 ({urgent+general})' if urgent+general else '告警')
        self.alarm_table.setRowCount(len(rows))
        for i,(_,severity,title,state,evidence) in enumerate(rows):
            color=('#ff6d7e' if severity=='紧急' else '#ffbd69') if state=='告警中' else '#7f8c9d' if state=='未判定' else '#71e3cc'
            for j,text in enumerate((severity,title,state,evidence)):cell(self.alarm_table,i,j,text,color)
        history=list(self.alarm_monitor.history);self.alarm_history.setRowCount(len(history))
        for i,(stamp2,severity,title,event,evidence) in enumerate(history):
            for j,text in enumerate((time.strftime('%H:%M:%S',time.localtime(stamp2)),severity,title,event,evidence)):cell(self.alarm_history,i,j,text)
        self.alarm_audio.update('紧急' if urgent else '一般' if general else None)
        self.alarm_audio_status.setText(self.alarm_audio.error or ('声音已静音；告警继续记录。' if not self.alarm_audio.enabled else '紧急：滴滴，停顿 3 秒；一般：嘟嘟，停顿 5 秒。紧急告警优先播放。'))
    def make_fields(self):
        p=QWidget();lay=QVBoxLayout(p);self.search=QLineEdit();self.search.setPlaceholderText('筛选状态名称、字段或分组…');self.search.textChanged.connect(self.filter_fields);lay.addWidget(self.search)
        self.fields_table=table(['分组','状态 / 字段','当前值','单位','质量','数据来源','距更新']);lay.addWidget(self.fields_table);self.field_keys=list(FIELDS);self.fields_table.setRowCount(len(self.field_keys));self.tabs.addTab(p,'全部状态')
    def make_joints(self):
        p=QWidget();lay=QVBoxLayout(p);info=label('12 个关节 · 角度 / 角速度来自 UDP；扭矩需要 SDK 0x0906；温度可来自 SDK 或日志。','muted');info.setWordWrap(True);lay.addWidget(info)
        self.joints=table(['关节','角度 rad','角速度 rad/s','扭矩 N·m','温度 °C']);self.joints.setRowCount(12);lay.addWidget(self.joints)
        lay.addWidget(label('灰色 = 已过期；“—” = 尚无数据。FL 左前 / FR 右前 / HL 左后 / HR 右后。','muted'));self.tabs.addTab(p,'关节数据')
    def make_diagnostics(self):
        p=QWidget();lay=QVBoxLayout(p);self.diagnostic=QTextEdit();self.diagnostic.setReadOnly(True);lay.addWidget(self.diagnostic,2)
        self.events=QTextEdit();self.events.setReadOnly(True);lay.addWidget(label('连接与采集事件','muted'));lay.addWidget(self.events,1);lay.addWidget(button('导出状态快照 JSON',self.export_state),alignment=Qt.AlignRight);self.tabs.addTab(p,'连接诊断')
    def make_mcp(self):
        p=QWidget();lay=QVBoxLayout(p);lay.setContentsMargins(0,20,0,0);lay.setSpacing(18);lay.addWidget(label('让 AI 读取机器狗的当前状态','title'));self.mcp_status=label('只读 MCP 服务启动中','pill');lay.addWidget(self.mcp_status)
        info=label('内嵌标准 MCP，仅监听本机并使用访问令牌。\nAI 和桌面界面读取同一份状态；字段均携带来源、单位和过期标记。');info.setWordWrap(True);lay.addWidget(info)
        tools=QTextEdit();tools.setReadOnly(True);tools.setPlainText('list_robots         设备与适配器能力\nget_robot_state     所有可读状态与新鲜度\nget_joint_states    12 个关节数据\nget_diagnostics     连接、服务及采集诊断\nget_camera_frame    最新画面（拒绝过期画面）\n\n资源：robot://current/state\n\n不提供运动工具、任意 SSH 命令或写入接口。');lay.addWidget(tools)
        lay.addWidget(button('复制 MCP 连接配置',self.copy_mcp,True),alignment=Qt.AlignLeft);info=label('支持 Streamable HTTP 客户端。配置含本机访问令牌，请仅用于可信客户端。','muted');info.setWordWrap(True);lay.addWidget(info);lay.addStretch();self.tabs.addTab(p,'AI / MCP')
    def connect_robot(self,password=None):
        if not isinstance(password,str):password=self.password.text() if self.password.isEnabled() else ''
        if self.ssh_input_state in ('在线','连接中'):
            self.notice.setText('设备正在连接或 SSH 已连接；需要重连时请先点击“断开连接”。');return
        self.alarm_audio.stop();self.alarm_monitor.reset()
        self.hold_button=None;self.hold_direction=None
        self.runtime.connect(self.profiles[self.select.currentIndex()],password);self.password.clear();self.show_password.setChecked(False);self.update_ssh_input('连接中' if password else '未连接');self.last_frame=0;self.pixmap=None;self.video.setText('正在连接摄像头…')
    def disconnect_robot(self):
        self.alarm_audio.stop()
        self.hold_button=None;self.hold_direction=None
        self.runtime.disconnect();self.update_ssh_input('已断开');self.pixmap=None;self.video.clear();self.video.setText('已断开连接');self.last_frame=0
    def update_ssh_input(self,state):
        if state==self.ssh_input_state:return
        previous=self.ssh_input_state;self.ssh_input_state=state
        locked=state in ('在线','连接中')
        self.password.setEnabled(not locked);self.show_password.setEnabled(not locked)
        if locked:
            self.show_password.setChecked(False);self.password.setEchoMode(QLineEdit.Normal)
            self.password.setText('SSH已连接' if state=='在线' else 'SSH连接中…')
        else:
            if previous in ('在线','连接中'):self.password.clear()
            self.password.setEchoMode(QLineEdit.Normal if self.show_password.isChecked() else QLineEdit.Password)
            self.password.setPlaceholderText('认证失败，请重新输入密码' if state=='认证失败' else '请输入密码')
    def save_profiles(self):(self.data_dir/'profiles.json').write_text(json.dumps({'profiles':self.profiles},ensure_ascii=False,indent=2),encoding='utf-8')
    def edit_profile(self):
        i=self.select.currentIndex();d=ProfileDialog(self.profiles[i],self)
        if d.exec()==QDialog.Accepted:
            self.profiles[i]=d.result_profile;self.select.setItemText(i,d.result_profile['name']);self.hostlabel.setText(d.result_profile['robot_ip']);self.save_profiles()
    def add_profile(self):
        d=ProfileDialog(self.profiles[self.select.currentIndex()],self)
        if d.exec()==QDialog.Accepted:self.profiles.append(d.result_profile);self.select.addItem(d.result_profile['name']);self.select.setCurrentIndex(len(self.profiles)-1);self.save_profiles()
    def filter_fields(self):
        q=self.search.text().lower()
        for r,k in enumerate(self.field_keys):self.fields_table.setRowHidden(r,q not in (k+FIELDS[k]['label']+FIELDS[k]['group']).lower())
    def refresh(self):
        s=self.runtime.snapshot();f=s['fields'];live=sum(e['status']=='live' for e in f.values());self.coverage.setText(f'{live} 项实时数据')
        self.update_ssh_input(s['connections'].get('SSH',{}).get('state','未连接'))
        for name,w in self.links.items():
            l=s['connections'].get(name,{});w.setText(f"{name} · {l.get('state','未连接')}");w.setToolTip(l.get('detail',''))
        if s['robot']:self.subtitle.setText(s['robot']['name']+' · '+s['robot']['robot_ip']+' · Lite 3 适配器')
        for k,(v,st) in self.cards.items():
            e=f[k];txt=display(k,e);v.setText(txt+(' '+e['unit'] if txt!='—' and e['unit'] else ''));size=21 if k=='basic' else 29;color='#7f8c9d' if e['status']=='stale' else '#edf6ff';v.setStyleSheet(f'font-size:{size}px;font-weight:700;color:{color};');st.setText(STATUS[e['status']]+' · '+e.get('source','等待上报'))
        for r,k in enumerate(self.quick_keys):
            e=f[k];cell(self.quick,r,0,e['label']);cell(self.quick,r,1,display(k,e)+(' '+e['unit'] if 'value'in e else ''));cell(self.quick,r,2,STATUS[e['status']],'#6bdcc8' if e['status']=='live' else '#8195af')
        for r,k in enumerate(self.field_keys):
            e=f[k];color='#74889e' if e['status'] in ('stale','unsupported','unavailable') else '#dfe8f3'
            for c,text in enumerate([e['group'],e['label']+' ['+k+']',display(k,e),e['unit'],STATUS[e['status']],e.get('source','—'),str(e.get('age_seconds','—'))+' s']):cell(self.fields_table,r,c,text,color)
        for r,j in enumerate(JOINTS):
            cell(self.joints,r,0,j)
            for c,prop in enumerate(('position','velocity','torque','temperature'),1):
                k=f'joint.{j}.{prop}';e=f[k];cell(self.joints,r,c,display(k,e),'#73e5cd' if e['status']=='live' else '#7f8c9d')
        txt=json.dumps({k:s[k] for k in ('connections','metadata','packet_counts','capabilities')},ensure_ascii=False,indent=2)
        if self.diagnostic.toPlainText()!=txt:self.diagnostic.setPlainText(txt)
        txt='\n'.join(time.strftime('%H:%M:%S',time.localtime(e['time']))+' '+e['text'] for e in s['events'])
        if self.events.toPlainText()!=txt:self.events.setPlainText(txt);self.events.verticalScrollBar().setValue(self.events.verticalScrollBar().maximum())
        self.mcp_status.setText(f'MCP · {self.bridge.state} {self.bridge.detail}');data,stamp,size=self.runtime.camera_frame()
        self.refresh_alarms(s,stamp)
        if data and stamp!=self.last_frame:p=QPixmap();p.loadFromData(data,'JPEG');self.pixmap=p;self.last_frame=stamp
        if self.pixmap:
            self.video.setPixmap(self.pixmap.scaled(self.video.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation));age=time.time()-stamp;self.camera_info.setText(f'{size} · 实时预览' if age<3 else f'画面已中断 · {age:.0f} 秒前');self.camera_info.setStyleSheet('color:#71e3cc' if age<3 else 'color:#ffb568')
        else:self.camera_info.setText('等待摄像头画面')
        control=s['control'];armed=control['armed']
        self.arm_box.blockSignals(True);self.arm_box.setChecked(armed);self.arm_box.blockSignals(False)
        self.arm_box.setEnabled(self.runtime.motion is not None)
        for widget in (self.command_execute,self.command_stop,self.command_estop):widget.setEnabled(self.runtime.motion is not None)
        speed=control.get('speed_level',1);self.speed_slider.blockSignals(True);self.speed_slider.setValue(speed);self.speed_slider.blockSignals(False)
        self.speed_text.setText(f'速度档位：{speed} / 5');self.speed_slider.setEnabled(self.runtime.motion is not None and not control['direction'] and not control['busy'])
        self.estop_button.setEnabled(self.runtime.motion is not None)
        for b in list(self.motion_buttons.values())+list(self.icon_motion_buttons.values()):b.setEnabled(armed and not control['busy'])
        basic=f['basic'];fresh=basic.get('status')=='live' and basic.get('age_seconds',99)<=.5
        code=basic.get('value');pose=MotionController.posture_from_basic(code) if fresh else None
        manual=fresh and code==98 and self.runtime.motion is not None and not control['busy']
        self.pose_choice.setVisible(manual);self.pose_choice.setEnabled(manual);self.pose_auto.setVisible(not manual)
        if control['busy']:pose_text='姿态切换中，等待状态更新'
        elif pose:pose_text='自动识别：'+{'sit':'趴下','stand':'站立'}[pose]
        elif not fresh:pose_text='姿态：等待有效实时状态'
        else:pose_text='当前状态无法识别站立／趴下（'+str(code)+'）'
        self.pose_auto.setText(pose_text)
        self.pose_choice.setToolTip('基本状态 98 无明确姿态映射，请现场确认；其他已识别状态自动读取。')
        desired={None:0,'sit':1,'stand':2}[control['operator_posture']]
        self.pose_choice.blockSignals(True);self.pose_choice.setCurrentIndex(desired);self.pose_choice.blockSignals(False)
        self.motion_status.setText(('控制心跳保持 · ' if control.get('session_active') else '')+control['message'])
        net=s['metadata'].get('network_config','')
        if s['connections'].get('UDP',{}).get('state')=='在线':self.notice.setText('遥控已启用 · 松开方向停止；窗口失焦锁定遥控。' if armed else '遥控默认关闭 · 启用后按住移动、松开停止；MCP 保持只读。')
        if net and s['connections'].get('UDP',{}).get('state')!='在线':self.notice.setText('UDP 尚未接入：机器人配置 '+net.replace('\n',' · ')+'。SSH 日志与视频可独立显示。')
    def save_frame(self):
        data,stamp,_=self.runtime.camera_frame()
        if not data or time.time()-stamp>3:QMessageBox.information(self,'暂无实时画面','请等待摄像头恢复后再保存。');return
        p,_=QFileDialog.getSaveFileName(self,'保存画面','lite3-camera.jpg','JPEG (*.jpg)')
        if p:
            try:Path(p).write_bytes(data)
            except OSError as e:QMessageBox.warning(self,'保存失败',str(e))
    def export_state(self):
        p,_=QFileDialog.getSaveFileName(self,'导出状态','robot-state.json','JSON (*.json)')
        if p:
            try:Path(p).write_text(json.dumps(self.runtime.snapshot(),ensure_ascii=False,indent=2),encoding='utf-8')
            except OSError as e:QMessageBox.warning(self,'导出失败',str(e))
    def copy_mcp(self):
        QApplication.clipboard().setText(json.dumps(self.bridge.config(),ensure_ascii=False,indent=2));QMessageBox.information(self,'已复制','MCP 配置已复制。服务仅在应用运行时可用。')
    def closeEvent(self,event):
        self.inspection_panel.shutdown()
        self.alarm_audio.close()
        self.timer.stop();self.hold_timer.stop();QApplication.instance().removeEventFilter(self);self.runtime.disconnect();self.bridge.stop();event.accept()
