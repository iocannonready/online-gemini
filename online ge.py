import streamlit as st
import os
import time
import shutil
import google.generativeai as genai
import uuid

# ================= 1. 配置区域 =================

HARDCODED_KEY = "" # 在此填入 Key，或使用 Streamlit Secrets (推荐)

# 获取 Key
try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    API_KEY = HARDCODED_KEY

# 页面配置 (去掉了图标，标题改得更简洁)
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

# 自动重发标记
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
        # 如果删除的是当前选中的，切到第一个
        if session_id == st.session_state.current_session_id:
            st.session_state.current_session_id = list(st.session_state.all_sessions.keys())[0]
        st.rerun()

def switch_session(session_id):
    st.session_state.current_session_id = session_id
    st.rerun()

# 获取当前会话数据
current_id = st.session_state.current_session_id
# 防止删除后 current_id 失效
if current_id not in st.session_state.all_sessions:
    current_id = list(st.session_state.all_sessions.keys())[0]
    st.session_state.current_session_id = current_id
current_session = st.session_state.all_sessions[current_id]

# ================= 3. 侧边栏 (全新设计) =================
with st.sidebar:
    # 顶部设置区
    with st.expander("⚙️ 设置与模型", expanded=True):
        selected_model = st.selectbox(
            "模型", 
            ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"],
            label_visibility="collapsed"
        )
        enable_search = st.toggle("🌍 联网搜索", value=False)
        temperature = st.slider("创造力", 0.0, 2.0, 0.7)

    st.divider()
    st.caption(f"SDK 版本: {genai.__version__}")
    # 会话列表标题 + 小加号
    col_header1, col_header2 = st.columns([4, 1])
    with col_header1:
        st.caption("会话列表")
    with col_header2:
        # 小加号按钮
        if st.button("➕", help="新建对话", use_container_width=True):
            create_new_session()

    # 循环渲染会话列表 (自定义样式)
    # 按创建顺序倒序排列(新的在上面) - 简单起见这里用字典顺序
    session_ids = list(st.session_state.all_sessions.keys())
    
    for sess_id in session_ids:
        sess_data = st.session_state.all_sessions[sess_id]
        
        # 每一行分两列：[标题按钮] [设置小按钮]
        c1, c2 = st.columns([0.85, 0.15])
        
        # 1. 标题按钮 (高亮当前选中的)
        is_active = (sess_id == current_id)
        btn_type = "primary" if is_active else "secondary"
        
        with c1:
            if st.button(sess_data["title"], key=f"btn_{sess_id}", type=btn_type, use_container_width=True):
                switch_session(sess_id)
        
        # 2. 设置小按钮 (Popover 弹出菜单)
        with c2:
            with st.popover("⋮", use_container_width=True):
                st.markdown("#### 管理会话")
                # 重命名
                new_name = st.text_input("名称", value=sess_data["title"], key=f"input_{sess_id}")
                if new_name != sess_data["title"]:
                    st.session_state.all_sessions[sess_id]["title"] = new_name
                    st.rerun()
                
                # 删除
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

# --- 初始化模型 (修复联网报错) ---
try:
    tools_config = []
    if enable_search:
        # 【关键修复】使用符合新版 SDK 的 Google Search 定义方式
        tools_config = [{"google_search": {}}] 

    generation_config = {"temperature": temperature}
    
    model = genai.GenerativeModel(
        selected_model,
        generation_config=generation_config,
        tools=tools_config
    )
    chat = model.start_chat(history=[])
except Exception as e:
    st.error(f"模型配置错误: {e}")
    st.caption("提示: 联网搜索报错通常是因为 SDK 版本过低，请在终端运行: pip install -U google-generativeai")
    st.stop()

# --- 聊天历史显示 ---
# 这一块代码放在上面，防止被底部的输入框挤上去
for msg in current_session['history']:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "usage" in msg:
            st.caption(f"📊 {msg['usage']}")

# --- 底部输入区与附件 ---

# 创建一个容器，放在聊天记录下方
bottom_container = st.container()

with bottom_container:
    # 1. 附件控制区 (极简风格)
    # 如果有已挂载的文件，显示一行小提示
    if current_session['files']:
        col_info, col_clear = st.columns([8, 2])
        with col_info:
            st.success(f"📎 已挂载 {len(current_session['files'])} 个文件 (将随下一次提问发送)")
        with col_clear:
            if st.button("卸载文件", key="clear_files"):
                current_session['files'] = []
                current_session['processed'] = False
                st.rerun()

    # 2. 上传按钮与输入框
    # 使用 popover 模拟“点击回形针弹出上传框”的效果
    with st.popover("📎 添加附件", help="上传图片或文档"):
        files = st.file_uploader("选择文件", accept_multiple_files=True, label_visibility="collapsed")
        if files:
            if st.button("确认上传", use_container_width=True):
                refs = upload_files(files)
                current_session['files'] = refs
                current_session['processed'] = False
                st.rerun()

    # 3. 聊天输入框 (Streamlit 强制置底)
    prompt = st.chat_input("输入问题...")

# --- 处理发送逻辑 ---
if st.session_state.trigger_regenerate:
    if current_session['history'] and current_session['history'][-1]['role'] == 'user':
        prompt = current_session['history'][-1]['content']
        current_session['history'].pop()
    st.session_state.trigger_regenerate = False

if prompt:
    current_session['history'].append({"role": "user", "content": prompt})
    st.rerun() # 强制刷新以立即显示用户的提问

# 页面刷新后，如果检测到最后一条是 user，则触发 AI 回复
if current_session['history'] and current_session['history'][-1]['role'] == 'user':
    # 这里不需要再显示 user message，因为上面已经渲染过了
    
    with st.chat_message("assistant"):
        box = st.empty()
        full_text = ""
        usage_str = ""
        
        try:
            # 构造 History
            history_for_api = []
            for h in current_session['history'][:-1]:
                history_for_api.append({
                    "role": "user" if h["role"] == "user" else "model",
                    "parts": [h["content"]]
                })
            chat.history = history_for_api
            
            # 发送
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
            
            # 自动重命名 (仅第一句)
            if len(current_session['history']) == 2:
                current_session['title'] = full_text[:10] + "..."
            
            st.rerun()
            
        except Exception as e:
            st.error(f"出错: {e}")

