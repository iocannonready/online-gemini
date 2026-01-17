import streamlit as st
import os
import time
import shutil
import uuid
# 使用 2026 最新版 SDK
from google import genai
from google.genai import types

# ================= 0. 版本元数据 =================
APP_VERSION = "v4.0.3-PRO"
BUILD_DATE = "2026-01-17"

# ================= 1. 初始化页面与安全配置 =================
st.set_page_config(
    page_title=f"凶哥哥的 AI {APP_VERSION}", 
    page_icon="🦁", 
    layout="wide"
)

# --- 安全读取 API KEY ---
try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    API_KEY = None

# 初始化 Session State
if "all_sessions" not in st.session_state:
    default_id = str(uuid.uuid4())
    st.session_state.all_sessions = {
        default_id: {
            "title": "新对话", 
            "history": [], 
            "files": [], 
            "processed": False 
        }
    }
    st.session_state.current_session_id = default_id

# 获取当前会话数据
def get_current_session():
    sid = st.session_state.current_session_id
    if sid not in st.session_state.all_sessions:
        sid = list(st.session_state.all_sessions.keys())[0]
        st.session_state.current_session_id = sid
    return st.session_state.all_sessions[sid]

current_session = get_current_session()

# ================= 2. 侧边栏 =================
with st.sidebar:
    st.title("🦁 凶哥哥的 AI")
    st.status(f"运行中 | {APP_VERSION}", state="complete")
    
    with st.expander("⚙️ 模型参数", expanded=True):
        model_list = [
            "gemini-1.5-pro",           # 处理 20-30 张文字图片首选
            "gemini-2.5-flash",         # 2026 稳定主力
            "gemini-3-flash-preview",   # 最新极速模型
            "gemini-2.0-flash",         # 经典型号
        ]
        selected_model = st.selectbox("选择模型", model_list, index=0)
        temperature = st.slider("创造力", 0.0, 2.0, 0.7)
        enable_search = st.toggle("🌍 联网搜索", value=True)

    st.divider()

    # 会话列表
    st.caption("💬 会话管理")
    if st.button("➕ 新建对话", use_container_width=True):
        nid = str(uuid.uuid4())
        st.session_state.all_sessions[nid] = {"title": "新对话", "history": [], "files": [], "processed": False}
        st.session_state.current_session_id = nid
        st.rerun()

    for sid in list(st.session_state.all_sessions.keys()):
        sess = st.session_state.all_sessions[sid]
        active = (sid == st.session_state.current_session_id)
        c1, c2 = st.columns([0.8, 0.2])
        with c1:
            if st.button(sess["title"], key=f"s_{sid}", type="primary" if active else "secondary", use_container_width=True):
                st.session_state.current_session_id = sid; st.rerun()
        with c2:
            with st.popover("⋮"):
                new_n = st.text_input("重命名", value=sess["title"], key=f"r_{sid}")
                if new_n != sess["title"]: sess["title"] = new_n; st.rerun()
                if st.button("🗑️", key=f"d_{sid}"):
                    if len(st.session_state.all_sessions) > 1: del st.session_state.all_sessions[sid]; st.rerun()

    # 版本显示
    st.markdown(f"<div style='position: fixed; bottom: 10px; font-size: 11px; color: gray;'>Version: {APP_VERSION} | SDK: {genai.__version__}</div>", unsafe_allow_html=True)

# ================= 3. 核心功能函数 =================

def get_client():
    if not API_KEY:
        st.error("❌ 未检测到 API KEY。请检查 Secrets。")
        return None
    return genai.Client(api_key=API_KEY)

def upload_handler_v4(client, files):
    temp_dir = "cloud_tmp"
    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir)
    
    uploaded_refs = []
    with st.status("🚀 正在深度解析附件...", expanded=True) as status:
        local_paths = []
        for f in files:
            p = os.path.join(temp_dir, f.name)
            with open(p, "wb") as b: b.write(f.getbuffer())
            local_paths.append(p)
        local_paths.sort() # 保证页码顺序
        
        for path in local_paths:
            try:
                r = client.files.upload(path=path)
                uploaded_refs.append(r)
                st.write(f"✅ 已载入: {os.path.basename(path)}")
            except Exception as e: st.error(f"出错: {e}")
        
        while True:
            ready = True
            for r in uploaded_refs:
                if client.files.get(name=r.name).state.name == "PROCESSING":
                    ready = False; break
            if ready: break
            time.sleep(2)
        status.update(label="✅ 附件解析完成", state="complete", expanded=False)
    
    shutil.rmtree(temp_dir, ignore_errors=True)
    return uploaded_refs

# ================= 4. 主对话界面 =================

client = get_client()
if client:
    # 1. 渲染历史
    for m in current_session["history"]:
        with st.chat_message(m["role"]): st.markdown(m["content"])

    # 2. 底部控制区 (文件+输入)
    chat_prompt = None
    
    with st.container():
        # 附件状态栏
        if current_session["files"]:
            st.info(f"📚 当前挂载了 {len(current_session['files'])} 张图片。AI 将在下一轮对话中阅读它们。")
            if st.button("🗑️ 清空附件"):
                current_session["files"] = []; current_session["processed"] = False; st.rerun()

        # 精简版上传布局：[浏览按钮] [极窄拖拽区] [聊天框]
        # 由于 Streamlit 布局限制，我们使用 3 列结构实现“紧凑型”
        col_btn, col_drag, col_chat = st.columns([0.1, 0.15, 0.75])
        
        with col_btn:
            # 这是一个纯按钮，点击打开 popover 里的文件浏览
            with st.popover("📎", help="点击浏览文件"):
                files = st.file_uploader("选择材料", accept_multiple_files=True, label_visibility="collapsed")
                if files and st.button("确认分析"):
                    current_session["files"] = upload_handler_v4(client, files)
                    current_session["processed"] = False
                    st.rerun()
        
        with col_drag:
            # 这是一个极小化的拖拽区，不写文字，只留一个窄条
            drag_files = st.file_uploader("Drag", accept_multiple_files=True, label_visibility="collapsed", key="drag_zone")
            if drag_files:
                 if st.button("处理拖入文件", use_container_width=True):
                    current_session["files"] = upload_handler_v4(client, drag_files)
                    current_session["processed"] = False
                    st.rerun()

        with col_chat:
            chat_prompt = st.chat_input("输入问题... (例如：整理这几张图的内容)")

    # 3. 对话执行逻辑
    if chat_prompt:
        current_session["history"].append({"role": "user", "content": chat_prompt})
        st.rerun()

    if current_session["history"] and current_session["history"][-1]["role"] == "user":
        with st.chat_message("assistant"):
            box = st.empty(); full = ""
            
            # --- 核心改进：显式多模态构造 ---
            payload = []
            
            # 如果有文件且还没被 AI 确认读过，注入提醒
            if current_session["files"] and not current_session["processed"]:
                # 在发送文件前，先塞一个“隐形”提示，增强 AI 的附件感知力
                payload.append("【系统通知：以下是用户上传的附件材料，请仔细阅读并根据此内容回答问题】")
                payload.extend(current_session["files"])
            
            # 加入用户的问题
            payload.append(current_session["history"][-1]["content"])

            try:
                # 构造对话历史
                h_objs = []
                for h in current_session["history"][:-1]:
                    h_objs.append(types.Content(
                        role="user" if h["role"] == "user" else "model",
                        parts=[types.Part(text=h["content"])]
                    ))

                # 联网工具
                tools = [types.Tool(google_search=types.GoogleSearch())] if enable_search else []

                # 创建 Chat
                chat_obj = client.chats.create(
                    model=selected_model,
                    history=h_objs,
                    config=types.GenerateContentConfig(temperature=temperature, tools=tools)
                )
                
                # 开始生成
                response = chat_obj.send_message_stream(message=payload)
                for chunk in response:
                    if chunk.text:
                        full += chunk.text
                        box.markdown(full + "▌")
                
                box.markdown(full)
                
                # 只有成功完成后，才标记文件已处理，并记录历史
                current_session["processed"] = True 
                current_session["history"].append({"role": "assistant", "content": full})
                
                # 自动标题
                if len(current_session["history"]) == 2:
                    current_session["title"] = current_session["history"][0]["content"][:10]
                st.rerun()

            except Exception as e:
                st.error(f"对话异常: {e}")
