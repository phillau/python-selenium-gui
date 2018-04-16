#encoding: utf-8
import wx
import os
import sys
import threading
import traceback
import wx.lib.agw.customtreectrl as CT
import ctypes
import inspect
import importlib
import xlrd
from selenium import webdriver
from time import sleep

importlib.reload(sys)

# 保存"编辑脚本文本框"内容的全局变量
global Contents
# 保存"控制台"内容的全局变量
global Consoles
# 保存前台传入的"并发线程数"的全局变量
global Threads
# 保存选中的批量脚本路径的全局变量
global BranchFiles

# 覆盖print方法，使print能够输出到gui工具控制台
def print(content):
    global_ui.Consoles.SetValue(str(global_ui.Consoles.GetValue())+str(content)+"\n")

'''excel工具方法'''
def getRowIndex(table, rowName):
    rowIndex = None
    for i in range(table.nrows):
        if(table.cell_value(i,0) == rowName):
            rowIndex = i
            break
    return rowIndex


def getColumnIndex(table, columnName):
    columnIndex = None
    # 同时配合也要修改这里为table.ncols或table.nrows
    for i in range(table.ncols):
        if(table.cell_value(0, i) == columnName):
            columnIndex = i
            break
    return columnIndex


def readExcelDataByName(fileName, sheetName):
    table = None
    errorMsg = ""
    try:
        data = xlrd.open_workbook(fileName)
        table = data.sheet_by_name(sheetName)
    except Exception as msg:
        errorMsg = msg
    return table, errorMsg


def readByColName(path,sheetName,colName):
    try:
        table = readExcelDataByName(path, sheetName)[0]
        # 修改这里的两个参数的位置可以确定是根据行名还是根据列表读取
        value = table.cell_value(1,getColumnIndex(table, colName),)
    except Exception as msg:
        raise RuntimeError('readByColName()方法为以第一行数据为键取第二行数据的值！')
    return value


def readByRowName(path,sheetName,rawName):
    try:
        table = readExcelDataByName(path, sheetName)[0]
        # 修改这里的两个参数的位置可以确定是根据行名还是根据列表读取
        value = table.cell_value(getRowIndex(table, rawName),1)
    except Exception as msg:
        raise RuntimeError('readByRowName()方法为以第一列数据为键取第二列数据的值')
    return value

def _async_raise(tid, exctype):
    """raises the exception, performs cleanup if needed"""
    tid = ctypes.c_long(tid)
    if not inspect.isclass(exctype):
        exctype = type(exctype)
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, ctypes.py_object(exctype))
    if res == 0:
        raise ValueError("invalid thread id")
    elif res != 1:
        # """if it returns a number greater than one, you're in trouble,
        # and you should call it again with exc=NULL to revert the effect"""
        ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, None)
        raise SystemError("PyThreadState_SetAsyncExc failed")

# '''传入线程对象引用杀死线程的方法'''
def stop_thread(thread):
    _async_raise(thread.ident, SystemExit)

class Go(threading.Thread):
    def __init__(self, content,threadname):
        threading.Thread.__init__(self, name=threadname)
        self.content = content

    def run(self):
        excepath = "temp.py"
        f = open(excepath, "w", encoding='UTF-8')
        f.write(self.content)
        try:
            with open(excepath, 'r', encoding='UTF-8') as f:
                exec(f.read())
        except PermissionError as e1:
            pass
        except Exception as e2:
            global_ui.Consoles.SetValue(traceback.format_exc())

class BranchGo(threading.Thread):
    def __init__(self, excepath):
        threading.Thread.__init__(self)
        self.excepath = excepath

    def run(self):
        try:
            with open(self.excepath, 'r', encoding='UTF-8') as f:
                exec(f.read())
        except PermissionError as e1:
            pass
        except Exception as e2:
            global_ui.Consoles.SetValue(traceback.format_exc())

'''在此线程中批量脚本相当于后台运行脚本，不会阻塞主线程'''
class WaitThread(threading.Thread):
    def __init__(self,thread_num, branch_files):
        threading.Thread.__init__(self)
        self.thread_num = thread_num
        self.branch_files = branch_files

    def run(self):
        for branch_file in self.branch_files:
            branch_go = BranchGo(branch_file)
            branch_go.start()
            while True:
                # 判断正在运行的线程数量,如果小于指定的thread_num则退出while循环,
                # 进入for循环启动新的进程.否则就一直在while循环进入死循环
                if len(threading.enumerate()) <= int(self.thread_num)+1:
                    break

'''在此线程中批量杀死线程和进程，不会阻塞主线程'''
class KillExplorer(threading.Thread):
    def __init__(self,threadname):
        threading.Thread.__init__(self, name=threadname)

    def run(self):
        try:
            # 在杀死浏览器和chromdriver进程之前先杀死批量执行脚本的线程，不然线程通过WaitThread中的while循环识别到当前线程数量小于指定数量会进入for循环继续执行剩下的脚本
            thread_list = threading.enumerate()
            for thread in thread_list:
                if (thread.getName() != "MainThread" and thread.getName()!="killthread"):
                    stop_thread(thread)
            # 调用杀死chromedriver进程和浏览器的方法
            killdriver()
        except Exception as e:
            global_ui.Consoles.SetValue(traceback.format_exc())

'''定义主动抛出异常的方法'''
def throws():
    raise RuntimeError('runtime error')

'''通过调用windows系统dos命令杀死chrome和chromedriver的方法'''
def killdriver():
    findchrome_cmd = 'wmic process where name="chrome.exe" get name,processid,parentprocessid'
    findchromedriver_cmd = 'wmic process where name="chromedriver.exe" get name,processid'
    killchromedriver_cmd = 'taskkill /im chromedriver.exe -f'
    dict_chrome = {}
    driver_pid_list = []

    findchrome_result = os.popen(findchrome_cmd ,mode='r')
    findchrome_res = findchrome_result.read()
    for line in findchrome_res.splitlines():
        if ("chrome.exe" in line):
            l = line.split()
            dict_chrome[l[1]] = l[2]

    findchromedriver_result = os.popen(findchromedriver_cmd ,mode='r')
    res_d = findchromedriver_result.read()
    for line in res_d.splitlines():
        if ("chromedriver.exe" in line):
            l = line.split()
            driver_pid_list.append(l[1])

    for driver_pid in driver_pid_list:
        for parent_pid in dict_chrome:
            if (parent_pid == driver_pid):
                kill_cmd = 'taskkill /pid ' + str(dict_chrome[parent_pid]) + ' -f'
                os.system(kill_cmd)

    os.system(killchromedriver_cmd)

class global_ui():
    # 封装弹出对话框方法
    def alert(message):
        dlg = wx.MessageDialog(None, message, "提示", wx.OK)  # 语法是(self, 内容, 标题, ID)
        dlg.ShowModal()  # 显示对话框
        dlg.Destroy()  # 当点击确定后关闭对话框
        throws()
    class edit_tab(wx.Notebook):
        def __init__(self, parent):
            wx.Notebook.__init__(self, parent)
            self.text_panel = wx.Panel(self, size=(1000, 1000))
            init_structure = "try:\n    path = \"请输入excel测试用例的路径\"\n    sheet_name = \"请输入sheet页名称\"\n    driver = webdriver.Chrome()\n    driver.implicitly_wait(10)\n    \nexcept:\n    raise RuntimeError(traceback)\nfinally:\n    driver.quit()"
            global_ui.Contents = wx.TextCtrl(self.text_panel, -1, init_structure, size=(960, 500), style=wx.TE_MULTILINE | wx.TE_NOHIDESEL | wx.TE_RICH2 | wx.TE_PROCESS_ENTER | wx.TE_PROCESS_TAB | wx.HSCROLL)
            global_ui.Consoles = wx.TextCtrl(self.text_panel, -1, "", pos=(0,520), size=(960, 215), style=wx.TE_MULTILINE | wx.TE_NOHIDESEL | wx.TE_RICH | wx.TE_PROCESS_ENTER |wx.TE_PROCESS_TAB | wx.HSCROLL)
            font = wx.Font(10, wx.SWISS, wx.NORMAL, wx.NORMAL)
            global_ui.Contents.SetFont(font)
            global_ui.Consoles.SetForegroundColour('red')

    class branch_tab(wx.Notebook):
        def __init__(self, parent):
            self.checked_items = []
            wx.Notebook.__init__(self, parent)
            self.top_panel = wx.Panel(self, size=(1000,40))
            wx.StaticText(self.top_panel, pos=(8, 14), label="并发线程数：")
            global_ui.Threads = wx.TextCtrl(self.top_panel, pos=(80,9), size=(50, 25), value="3")
            branch_button = wx.Button(self.top_panel, pos=(150, 5), label="执行选中")
            refresh_button = wx.Button(self.top_panel, pos=(250, 5), label="刷新")
            self.Bind(wx.EVT_BUTTON, self.branch_start, branch_button)
            self.Bind(wx.EVT_BUTTON, self.branch_refresh, refresh_button)
            self.load_tree(self)

        # 批量执行任务
        def branch_start(self, event):
            thread_num = global_ui.Threads.GetValue()
            if (thread_num.isdigit()):
                if (int(thread_num) < 1) or (int(thread_num) > 3):
                    global_ui.alert("线程数必须在1到3个线程之间！")
            elif not (thread_num.isdigit()):
                global_ui.alert("线程数必须为正整数类型！")
            try:
                branch_files = global_ui.BranchFiles
            except Exception as e:
                global_ui.alert("请选择需要批量执行的脚本！")
            wait_thread = WaitThread(thread_num,branch_files)
            wait_thread.start()

        '''刷新目录树'''
        def branch_refresh(self, event):
            # 刷新之前先将custom_tree资源释放然后重新加载文件树
            self.custom_tree.Destroy()
            self.load_tree(self)

        '''加载目录树'''
        def load_tree(self, event):
            self.custom_tree = CT.CustomTreeCtrl(self, pos=(0, 40), size=(960, 705), agwStyle=wx.TR_DEFAULT_STYLE)
            self.root = self.custom_tree.AddRoot("脚本", ct_type=1)
            self.item_list = []
            self.item_list.append(self.root)

            def travelTree(currentPath):
                if not os.path.exists(currentPath):
                    return
                if os.path.isfile(currentPath):
                    for index, it in enumerate(self.item_list):
                        cp = ""
                        for i, c in enumerate(currentPath.split("\\", 30)):
                            if i == len(currentPath.split("\\", 30)) - 1:
                                break
                            cp = cp + c + "\\"
                        p = cp[:-1]
                        if (it._text == p):
                            file_dict = {}
                            file_name = currentPath.split("\\", 30)[-1]
                            file_dict[currentPath] = file_name
                            self.custom_tree.AppendItem(self.item_list[index], currentPath, ct_type=1)
                            break
                elif os.path.isdir(currentPath):
                    for index, it in enumerate(self.item_list):
                        cp = ""
                        for i, c in enumerate(currentPath.split("\\", 30)):
                            if i == len(currentPath.split("\\", 30)) - 1:
                                break
                            cp = cp + c + "\\"
                        p = cp[:-1]
                        if (it._text == p):
                            dir_dict = {}
                            dir_name = currentPath.split("\\", 30)[-1]
                            dir_dict[currentPath] = dir_name
                            self.item = self.custom_tree.AppendItem(self.item_list[index], currentPath, ct_type=1)
                            self.item_list.append(self.item)
                            break
                    pathList = os.listdir(currentPath)
                    for eachPath in pathList:
                        travelTree(currentPath + '\\' + eachPath)

            travelTree('脚本')
            self.custom_tree.ExpandAll()
            self.custom_tree.Bind(CT.EVT_TREE_ITEM_CHECKED, self.checked_item)

        def checked_item(self, event):
            # 只要树控件中的任意一个复选框状态有变化就会响应这个函数
            if self.custom_tree.IsItemChecked(event.GetItem()):
                if len(self.get_childs(event.GetItem())) > 0:
                    self.custom_tree.CheckChilds(event.GetItem())
                    # 递归选中文件夹下的所有文件目录
                    def loop_item(items):
                        for item in self.get_childs(items):
                            self.checked_items.append(self.custom_tree.GetItemText(item))
                            loop_item(item)
                    loop_item(event.GetItem())
                else:
                    self.checked_items.append(self.custom_tree.GetItemText(event.GetItem()))
            else:
                for item in self.get_childs(event.GetItem()):
                    try:
                        self.custom_tree.CheckItem(item, False)
                        self.checked_items.remove(self.custom_tree.GetItemText(item))
                    except Exception as e:
                        pass
                try:
                    self.checked_items.remove(self.custom_tree.GetItemText(event.GetItem()))
                except Exception as e:
                    pass
            # list去重
            self.checked_items = list(set(self.checked_items))
            global_ui.BranchFiles = self.checked_items
            # print(self.checked_items)

        def get_childs(self, item_obj):
            self.item_list = []
            (item, cookie) = self.custom_tree.GetFirstChild(item_obj)
            while item:
                self.item_list.append(item)
                (item, cookie) = self.custom_tree.GetNextChild(item_obj, cookie)
            return self.item_list

    class button1(wx.Panel):
        def __init__(self, parent):
            wx.Panel.__init__(self, parent)
            wx.Button(self, pos=(9, 10), label="正常模式")

    class button2(wx.Panel):
        def __init__(self, parent):
            wx.Panel.__init__(self, parent)
            b2 = wx.Button(self, pos=(9, 10), label="加载脚本")
            self.Bind(wx.EVT_BUTTON, self.onOpenFile, b2)

        # 加载脚本的方法
        def onOpenFile(self, event):
            dlg = wx.FileDialog(
                                self, message="选择文件",
                                defaultFile="",
                                wildcard="Python source (*.py; *.pyc)|*.py;*.pyc",
                                style=wx.FD_OPEN
                                )
            if dlg.ShowModal() == wx.ID_OK:
                tmp = ""
                paths = dlg.GetPaths()
                for path in paths:
                    tmp = tmp + path
                file = open(tmp, 'r', encoding='UTF-8')
                file_content = file.read()
                global_ui.Contents.SetValue(file_content)
                file.close()
            dlg.Destroy()

    class button3(wx.Panel):
        def __init__(self, parent):
            wx.Panel.__init__(self, parent)
            b3 = wx.Button(self, pos=(9, 10), label="保存脚本")
            self.Bind(wx.EVT_BUTTON, self.onSaFile, b3)

        # 保存脚本的方法
        def onSaFile(self, event):
            dlg = wx.FileDialog(self,
                                message="保存文件",
                                defaultFile="",
                                wildcard="Python source (*.py; *.pyc)|*.py;*.pyc",
                                style=wx.FD_SAVE
                                )
            if dlg.ShowModal() == wx.ID_OK:
                filename = ""
                paths = dlg.GetPaths()
                for path in paths:
                    filename = filename + path
                file = open(filename, 'w', encoding='UTF-8')
                file.write(global_ui.Contents.GetValue())
                file.close()
            dlg.Destroy()

    class button4(wx.Panel):
        def __init__(self, parent):
            wx.Panel.__init__(self, parent)
            wx.Button(self, pos=(9, 10), label="保存组件")

    class button5(wx.Panel):
        def __init__(self, parent):
            wx.Panel.__init__(self, parent)
            b5 = wx.Button(self, pos=(9, 10), label="清除驱动进程")
            self.Bind(wx.EVT_BUTTON, self.kill, b5)

        def kill(self, event):
            kill_explorer = KillExplorer("killthread")
            kill_explorer.start()
            # global_ui.alert("正在关闭进程，请稍候...")

    class button6(wx.Panel):
        def __init__(self, parent):
            wx.Panel.__init__(self, parent)
            b6 = wx.Button(self, pos=(9, 10), label="启动任务")
            self.Bind(wx.EVT_BUTTON, self.start, b6)

         # 启动任务的方法
        def start(self, event):
            content = global_ui.Contents.GetValue()
            go = Go(content, "go")
            go.start()

if __name__ == '__main__':
    app = wx.App(False)
    frame = wx.Frame(None, title="中科软UI自动化平台", size=(1000, 820))
    frame.SetIcon(wx.Icon('sino.ico',wx.BITMAP_TYPE_ICO))
    pa = wx.Panel(frame)
    hbox = wx.BoxSizer(wx.HORIZONTAL)
    hbox.Add(global_ui.button1(pa), 0, wx.TB_TOP)
    hbox.Add(global_ui.button2(pa), 0, wx.TB_TOP)
    hbox.Add(global_ui.button3(pa), 0, wx.TB_TOP)
    hbox.Add(global_ui.button4(pa), 0, wx.TB_TOP)
    hbox.Add(global_ui.button5(pa), 0, wx.TB_TOP)
    hbox.Add(global_ui.button6(pa), 0, wx.TB_TOP)
    pa.SetSizer(hbox)
    nb = wx.Notebook(pa, pos=(10, 50), size=(965, 1000))
    nb.AddPage(global_ui.edit_tab(nb), "编辑脚本")
    nb.AddPage(global_ui.branch_tab(nb), "批量执行")
    frame.Show()
    app.MainLoop()