"""Room inspection panel. Capture continues while the operator uses Overview."""
import json
import os
import shutil
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QSpinBox, QPushButton, QCheckBox, QProgressBar, QTableWidget,
    QTableWidgetItem, QHeaderView, QTextBrowser, QFileDialog, QMessageBox,
    QAbstractItemView,
)
from .inspection import InspectionSession, InspectionError, DEFAULT_MODEL, LIMITATION


class InspectionPanel(QWidget):
    def __init__(self, runtime, data_dir, parent=None):
        super().__init__(parent)
        self.runtime = runtime
        self.data_dir = Path(data_dir)
        self.session = InspectionSession(self.data_dir / 'inspections', runtime.camera_frame)
        self.settings_file = self.data_dir / 'inspection-settings.json'
        try:
            settings = json.loads(self.settings_file.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            settings = {}
        self.last_report = None
        self.last_frame_count = -1
        outer = QVBoxLayout(self)
        outer.setSpacing(12)
        title = QLabel('房间巡检 · 人工遥控 / 云端物品分析')
        title.setObjectName('title')
        outer.addWidget(title)
        intro = QLabel('填写 API 配置 → 开始巡检 → 切换到运动遥控人工巡看 → 结束巡检并分析 → 查看物品清单与截图。\n'
                       '自动采集在切换页面后继续；达到图片上限或 10 分钟后自动结束采集并分析，采集结束不会代替你停止遥控。')
        intro.setWordWrap(True)
        outer.addWidget(intro)
        config = QHBoxLayout()
        form = QFormLayout()
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText('OpenAI API Key（仅本次运行，也可使用 OPENAI_API_KEY 环境变量）')
        form.addRow('API Key', self.key)
        self.model = QLineEdit(str(settings.get('model', DEFAULT_MODEL)))
        form.addRow('视觉模型', self.model)
        config.addLayout(form, 3)
        limits = QFormLayout()
        self.interval = QSpinBox()
        self.interval.setRange(2, 60)
        self.interval.setValue(self._number(settings.get('interval'), 5, 2, 60))
        self.interval.setSuffix(' 秒')
        self.limit = QSpinBox()
        self.limit.setRange(1, 24)
        self.limit.setValue(self._number(settings.get('limit'), 20, 1, 24))
        self.limit.setSuffix(' 张')
        limits.addRow('自动采图间隔', self.interval)
        limits.addRow('本轮图片上限', self.limit)
        config.addLayout(limits, 1)
        outer.addLayout(config)
        self.consent = QCheckBox('允许将本轮图片上传到 OpenAI 分析（产生 API 费用）；API Key 不保存到磁盘。')
        outer.addWidget(self.consent)
        controls = QHBoxLayout()
        self.start_button = QPushButton('开始巡检')
        self.start_button.setObjectName('primary')
        self.finish_button = QPushButton('结束巡检并分析')
        self.import_button = QPushButton('导入照片分析')
        self.retry_button = QPushButton('重试分析')
        self.cancel_button = QPushButton('取消任务')
        self.export_button = QPushButton('导出报告和截图')
        for widget, action in (
            (self.start_button, self.start), (self.finish_button, self.finish),
            (self.import_button, self.import_images), (self.retry_button, self.retry),
            (self.cancel_button, self.cancel), (self.export_button, self.export),
        ):
            widget.clicked.connect(action)
            controls.addWidget(widget)
        outer.addLayout(controls)
        self.status = QLabel('尚未开始巡检')
        self.status.setWordWrap(True)
        outer.addWidget(self.status)
        self.progress = QProgressBar()
        outer.addWidget(self.progress)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(['物品 / 类别', '可见数量下限', '颜色 / 外观', '画面位置', '可见文字', '识别把握', '截图依据 / 不确定性'])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.cellDoubleClicked.connect(self.open_evidence)
        outer.addWidget(self.table, 3)
        self.details = QTextBrowser()
        self.details.setPlaceholderText('报告生成后在此显示场景总结。双击物品行可打开对应截图。')
        self.details.setMinimumHeight(100)
        outer.addWidget(self.details, 1)
        note = QLabel(LIMITATION)
        note.setObjectName('muted')
        note.setWordWrap(True)
        outer.addWidget(note)
        self.poll = QTimer(self)
        self.poll.timeout.connect(self.refresh)
        self.poll.start(400)
        self.refresh()

    @staticmethod
    def _number(value, default, low, high):
        return value if type(value) is int and low <= value <= high else default

    def credentials(self):
        if not self.consent.isChecked():
            raise InspectionError('请先勾选本轮图片上传授权。')
        key = self.key.text().strip() or os.environ.get('OPENAI_API_KEY', '').strip()
        model = self.model.text().strip()
        if not key:
            raise InspectionError('请填写 OpenAI API Key。SSH 密码不能用于图像分析。')
        if not model:
            raise InspectionError('请填写支持图像输入和结构化输出的模型名称。')
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings_file.write_text(json.dumps({'model': model, 'interval': self.interval.value(),
                                                  'limit': self.limit.value()}, ensure_ascii=False, indent=2), encoding='utf-8')
        return key, model

    def _call(self, action):
        try:
            action()
        except (InspectionError, OSError) as error:
            QMessageBox.warning(self, '巡检未启动', str(error) if isinstance(error, InspectionError) else '本机目录无法写入，请检查磁盘空间和权限。')
        self.refresh()

    def start(self):
        def action():
            key, model = self.credentials()
            self.session.start(key, model, self.interval.value(), self.limit.value())
        self._call(action)

    def finish(self):
        self.session.finish()
        self.refresh()

    def cancel(self):
        self.session.cancel()
        self.refresh()

    def import_images(self):
        # The dialog is opened before creating a session; cancelling changes nothing.
        files, _ = QFileDialog.getOpenFileNames(self, '选择本轮巡检照片', '', '图片 (*.jpg *.jpeg *.png *.webp)')
        if files:
            def action():
                key, model = self.credentials()
                self.session.import_and_analyze(files, key, model)
            self._call(action)

    def retry(self):
        def action():
            key, model = self.credentials()
            self.session.retry(key, model)
        self._call(action)

    def refresh(self):
        snap = self.session.snapshot()
        worker_alive = bool(self.session.thread and self.session.thread.is_alive())
        active = snap['state'] in ('capturing', 'importing', 'analyzing') or worker_alive
        count = len(snap['frames'])
        skip = snap['skipped']
        self.status.setText(snap['message'] + f'\n已采集 {count} 张；跳过重复 {skip["duplicate"]} / 模糊 {skip["blur"]} / 无新鲜画面 {skip["stale"]}。'
                            + ('\n保存位置：' + snap['directory'] if snap['directory'] else ''))
        self.start_button.setEnabled(not active)
        self.import_button.setEnabled(not active)
        self.finish_button.setEnabled(snap['state'] == 'capturing' and not self.session.finish_event.is_set())
        self.cancel_button.setEnabled(snap['state'] in ('capturing', 'importing', 'analyzing'))
        self.retry_button.setEnabled(not active and count > 0 and snap['state'] in ('error', 'cancelled', 'complete'))
        self.export_button.setEnabled(snap['report'] is not None and not active)
        for widget in (self.key, self.model, self.interval, self.limit, self.consent):
            widget.setEnabled(not active)
        if snap['state'] in ('analyzing', 'importing'):
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, snap['limit'])
            self.progress.setValue(count)
        if snap['report'] != self.last_report:
            self.last_report = snap['report']
            self.table.setRowCount(0)
            self.details.clear()
            if self.last_report:
                report = self.last_report
                self.table.setRowCount(len(report['items']))
                for row, item in enumerate(report['items']):
                    values = [item['name'] + ' / ' + item['category'], '至少 ' + str(item['count_min']),
                              '；'.join(v for v in (item['color'], item['description']) if v), item['location'],
                              item['visible_text'], item['confidence'],
                              '、'.join(item['evidence_frame_ids']) + ('；' + item['uncertainties'] if item['uncertainties'] else '')]
                    for column, value in enumerate(values):
                        cell = QTableWidgetItem(value)
                        cell.setToolTip(value)
                        self.table.setItem(row, column, cell)
                self.details.setPlainText(report['summary'] + '\n\n' + '\n'.join(report['limitations']) + '\n\n' + LIMITATION)

    def open_evidence(self, row, column=0):
        snap = self.session.snapshot()
        if not snap['report'] or not 0 <= row < len(snap['report']['items']):
            return
        frame_id = snap['report']['items'][row]['evidence_frame_ids'][0]
        frame = next(f for f in snap['frames'] if f['id'] == frame_id)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(snap['directory']) / frame['file'])))

    def export(self):
        snap = self.session.snapshot()
        if not snap['report']:
            return
        parent = QFileDialog.getExistingDirectory(self, '选择报告导出目录')
        if not parent:
            return
        destination = Path(parent) / ('房间巡检-' + Path(snap['directory']).name)
        try:
            shutil.copytree(snap['directory'], destination)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(destination / 'report.html')))
        except FileExistsError:
            QMessageBox.information(self, '目录已存在', '该轮报告已经导出，请选择其他目录。')
        except OSError:
            QMessageBox.warning(self, '导出失败', '请检查目录权限和磁盘空间。原始报告仍保留在保存位置。')

    def shutdown(self):
        self.poll.stop()
        if self.session.thread and self.session.thread.is_alive():
            self.session.cancel()
        self.key.clear()
