"""Run with the bundled Python, or a virtualenv populated from requirements.txt."""
import os,sys,site
from pathlib import Path
ROOT=Path(__file__).resolve().parent
site.addsitedir(str(ROOT/'vendor'));sys.path.insert(0,str(ROOT/'vendor'))
# Prevent unrelated native tools (e.g. Poppler ICU) from shadowing Windows DLLs.
os.environ['PATH']=os.pathsep.join([str(ROOT/'vendor'/'PySide6'),str(Path(sys.executable).parent),str(Path(os.environ['WINDIR'])/'System32'),os.environ['WINDIR']])
import PyInstaller.__main__
PyInstaller.__main__.run([
    str(ROOT/'main.py'),'--name','RoverDesk','--noconfirm','--clean','--windowed','--onedir',
    '--distpath',str(ROOT/'release'),'--workpath',str(ROOT/'build'),'--specpath',str(ROOT),
    '--paths',str(ROOT/'vendor'),'--icon',str(ROOT/'rover.ico'),
    '--add-data',str(ROOT/'profiles.json')+';.',
    '--add-data',str(ROOT/'known_hosts')+';.',
    '--add-data',str(ROOT/'rover/remote_reader.py')+';rover',
    '--collect-all','av','--collect-submodules','uvicorn',
    '--collect-data','mcp','--hidden-import','mcp.server','--collect-all','mcp_types',
    '--exclude-module','mcp.cli',
    '--exclude-module','matplotlib','--exclude-module','pandas',
    '--exclude-module','scipy','--exclude-module','IPython',
])
