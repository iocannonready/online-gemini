import streamlit as st
import os
import time
import shutil
import google.generativeai as genai
import uuid
# 【新增】引入底层协议库，彻底解决 Unknown field 报错
from google.generativeai import protos 

# ================= 1. 配置区域 =================

HARDCODED_KEY = "" # 留空，使用 Streamlit Secrets

try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    API_KEY = HARDCODED_KEY

st.set_page_config(
    page_title="AI 助手",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ================= 2. 会话管理逻辑 =================

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

if "trigger_regenerate" not in st.session_state:
    st.session_state.trigger_regenerate = False

def create_new_session():
    new_id = str(uuid.uuid4())
    st.session_state.all_sessions[new_id] = {
        "title": "新对话",
        "history": [],
        "files": [],
        "processed": False
    }
    st.session_state.current_session_id = new_id
    st.rerun()

def delete_session(session_id):
    if len(st.session_state.all_sessions) > 1:
        del st.session_state.all_sessions[session_id]
        if session_id == st.session_state.current_session_id:
            st.session_state.current_session_id = list(st.session_state.all_sessions.keys())[0]
        st.rerun()

def switch_session(session_id):
    st.session_state.current_session_id = session_id
    st.rerun()

current_id = st.session_state.current_session_id
if current_id not in st.session_state.all_sessions:
    current_id = list(st.session_state.all_sessions.keys())[0]
    st.session_state.current_session_id = current_id
current_session = st.session_state.all_sessions[current_id]

# ================= 3. 侧边栏 =================
with st.sidebar:
    with st.expander("⚙️ 设置与模型", expanded=True):
        selected_model = st.selectbox(
            "模型", 
            ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"],
            label_visibility="collapsed"
        )
        # 🟢 移除了联网开关，默认就是开启的
        temperature = st.slider("创造力", 0.0, 2.0, 0.7)

    st.divider()

    col_header1, col_header2 = st.columns([4, 1])
    with col_header1: st.caption("会话列表")
    with col_header2:
        if st.button("➕", help="新建对话", use_container_width=True):
            create_new_session()

    session_ids = list(st.session_state.all_sessions.keys())
    for sess_id in session_ids:
        sess_data = st.session_state.all_sessions[sess_id]
        c1, c2 = st.columns([0.85, 0.15])
        is_active = (sess_id == current_id)
        btn_type = "primary" if is_active else "secondary"
        
        with c1:
            if st.button(sess_data["title"], key=f"btn_{sess_id}", type=btn_type, use_container_width=True):
                switch_session(sess_id)
        
        with c2:
            with st.popover("⋮", use_container_width=True):
                st.markdown("#### 管理")
                new_name = st.text_input("名称", value=sess_data["title"], key=f"input_{sess_id}")
                if new_name != sess_data["title"]:
                    st.session_state.all_sessions[sess_id]["title"] = new_name
                    st.rerun()
                if st.button("🗑️ 删除", key=f"del_{sess_id}", type="primary"):
                    delete_session(sess_id)

# ================= 4. 功能函数 =================

def configure_env():
    if not API_KEY: return False
    genai.configure(api_key=API_KEY)
    return True

def upload_files(uploaded_files):
    temp_dir = "cloud_temp"
    if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    
    refs = []
    status = st.empty()
    local_paths = []
    for f in uploaded_files:
        path = os.path.join(temp_dir, f.name)
        with open(path, "wb") as buffer: buffer.write(f.getbuffer())
        local_paths.append(path)
    local_paths.sort()
    
    for i, path in enumerate(local_paths):
        status.caption(f"正在上传 {i+1}/{len(local_paths)}...")
        try:
            f = genai.upload_file(path)
            refs.append(f)
        except Exception as e:
            st.error(f"上传失败: {e}")
    
    if refs:
        status.caption("正在解析...")
        while True:
            ready = True
            for r in refs:
                if genai.get_file(r.name).state.name == "PROCESSING":
                    ready = False; break
            if ready: break
            time.sleep(1)
            
    status.empty()
    shutil.rmtree(temp_dir)
    return refs

# ================= 5. 主界面逻辑 =================

if not configure_env():
    st.warning("⚠️ 请配置 API Key")
    st.stop()

# --- 初始化模型 (核心修复区域) ---
try:
    # 🟢 修复1：直接使用 protos 绕过 SDK 字典检查 (解决 Unknown field 报错)
    # 🟢 修复2：不再判断 if enable_search，直接默认开启 (解决 NameError 报错)
    
    # 定义工具：永远开启 Google 搜索
    tools_config = [
        protos.Tool(
            google_search=protos.GoogleSearch()
        )
    ]

    generation_config = {"temperature": temperature}
    
    model = genai.GenerativeModel(
        selected_model,
        generation_config=generation_config,
        tools=tools_config
    )
    
    chat = model.start_chat(history=[])

except Exception as e:
    st.error(f"模型配置错误: {e}")
    st.caption(f"SDK Version: {genai.__version__}")
    st.stop()

# --- 聊天显示 ---
for msg in current_session['history']:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "usage" in msg:
            st.caption(f"📊 {msg['usage']}")

# --- 底部输入区 ---
bottom_container = st.container()
with bottom_container:
    if current_session['files']:
        col_info, col_clear = st.columns([8, 2])
        with col_info:
            st.success(f"📎 已挂载 {len(current_session['files'])} 个文件")
        with col_clear:
            if st.button("卸载文件", key="clear_files"):
                current_session['files'] = []
                current_session['processed'] = False
                st.rerun()

    with st.popover("📎 添加附件", help="上传文件"):
        files = st.file_uploader("选择文件", accept_multiple_files=True, label_visibility="collapsed")
        if files:
            if st.button("确认上传", use_container_width=True):
                refs = upload_files(files)
                current_session['files'] = refs
                current_session['processed'] = False
                st.rerun()

    prompt = st.chat_input("输入问题...")

# --- 发送逻辑 ---
if st.session_state.trigger_regenerate:
    if current_session['history'] and current_session['history'][-1]['role'] == 'user':
        prompt = current_session['history'][-1]['content']
        current_session['history'].pop()
    st.session_state.trigger_regenerate = False

if prompt:
    current_session['history'].append({"role": "user", "content": prompt})
    st.rerun()

if current_session['history'] and current_session['history'][-1]['role'] == 'user':
    with st.chat_message("assistant"):
        box = st.empty()
        full_text = ""
        usage_str = ""
        
        try:
            history_for_api = []
            for h in current_session['history'][:-1]:
                history_for_api.append({
                    "role": "user" if h["role"] == "user" else "model",
                    "parts": [h["content"]]
                })
            chat.history = history_for_api
            
            if current_session['files'] and not current_session['processed']:
                parts = [current_session['history'][-1]['content']] + current_session['files']
                response = chat.send_message(parts, stream=True)
                current_session['processed'] = True
            else:
                response = chat.send_message(current_session['history'][-1]['content'], stream=True)
            
            for chunk in response:
                full_text += chunk.text
                box.markdown(full_text + "▌")
                if chunk.usage_metadata:
                    in_t = chunk.usage_metadata.prompt_token_count
                    out_t = chunk.usage_metadata.candidates_token_count
                    usage_str = f"Token: {in_t}+{out_t}={in_t+out_t}"

            box.markdown(full_text)
            
            msg_data = {"role": "assistant", "content": full_text}
            if usage_str: msg_data["usage"] = usage_str
            current_session['history'].append(msg_data)
            
            if len(current_session['history']) == 2:
                current_session['title'] = full_text[:10] + "..."
            
            st.rerun()
            
        except Exception as e:
            st.error(f"出错: {e}")
