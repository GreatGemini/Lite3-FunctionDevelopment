"""Fixed local vocabulary for typed or future transcribed commands."""
import re
import unicodedata
COMMANDS={'起立':1,'趴下':2,'前进':3,'后退':4,'左横移':5,'右横移':6,
          '停止':7,'低头':8,'抬头':9,'向左看':11,'向右看':12,
          '左转90度':13,'右转90度':14,'转身180度':15,'打招呼':22}
ALIASES={'站起来':'起立','坐下':'趴下','向前走':'前进','向后退':'后退',
         '向左横移':'左横移','向右横移':'右横移','停下':'停止',
         '左看':'向左看','右看':'向右看','左转九十度':'左转90度',
         '右转九十度':'右转90度','转身一百八十度':'转身180度','你好':'打招呼'}
def parse_command(text):
    text=unicodedata.normalize('NFKC',text).strip()
    text=re.sub(r'\s+','',text).replace('°','度').rstrip('。.!！')
    if text.startswith('机器狗'):text=text[3:]
    text=ALIASES.get(text,text)
    if text not in COMMANDS:raise ValueError('未识别口令：请选择单条指令，不支持组合句或否定句。')
    return text,COMMANDS[text]
