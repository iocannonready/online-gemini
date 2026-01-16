import streamlit as st
import os
import time
import shutil
import google.generativeai as genai
import uuid # 用于生成唯一的对话ID

# ================= 1. 配置区域 =================

# 【方式 A】安全做法 (推荐)：在 Streamlit 网页后台填 Secrets，这里不用改
# 【方式 B】简单做法：直接把你的 Key 填在下面的引号里
HARDCODED_KEY = "" 

# 尝试获取 Key：优先从云端 Secrets 获取，取不到就用代码里写的
try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    API_KEY = HARDCODED_KEY

# 页面基础配置
st.set_page_config(
    page_title="凶哥哥的AI",
    page_icon="🦁",
    layout="wide"
)

# ================= 2. 会话管理逻辑 (多对话功能) =================

if "all_sessions" not in st.session_state:
    # 初始化默认会话
    default_id = str(uuid.uuid4())
    st.session_state.all_sessions = {
        default_id: {
            "title": "新对话 1", 
            "history": [], 
            "files": [],     # 这一轮对话挂载的文件
            "processed": False 
        }
    }
    st.session_state.current_session_id = default_id

def create_new_session():
    new_id = str(uuid.uuid4())
    count = len(st.session_state.all_sessions) + 1
    st.session_state.all_sessions[new_id] = {
        "title": f"新对话 {count}",
        "history": [],
        "files": [],
        "processed": False
    }
    st.session_state.current_session_id = new_id
    st.rerun()

def delete_session(session_id):
    if len(st.session_state.all_sessions) > 1:
        del st.session_state.all_sessions[session_id]
        # 如果删除的是当前会话，切换到第一个
        if session_id == st.session_state.current_session_id:
            st.session_state.current_session_id = list(st.session_state.all_sessions.keys())[0]
        st.rerun()

# 获取当前会话的数据
current_id = st.session_state.current_session_id
current_session = st.session_state.all_sessions[current_id]

# ================= 3. 侧边栏 =================
with st.sidebar:
    st.title("🦁 凶哥哥的AI")
    
    # --- 模型选择 ---
    selected_model = st.selectbox(
        "当前模型", 
        ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"],
        index=0
    )
    
    st.divider()
    
    # --- 多对话管理 ---
    st.subheader("💬 会话列表")
    
    if st.button("➕ 新建对话", use_container_width=True):
        create_new_session()
        
    # 显示所有会话的单选按钮
    session_ids = list(st.session_state.all_sessions.keys())
    session_titles = [st.session_state.all_sessions[k]["title"] for k in session_ids]
    
    # 找到当前 ID 在列表中的索引
    current_index = session_ids.index(current_id) if current_id in session_ids else 0
    
    selected_index = st.radio(
        "选择历史记录:", 
        range(len(session_ids)), 
        format_func=lambda i: session_titles[i],
        index=current_index,
        label_visibility="collapsed"
    )
    
    # 如果用户切换了单选框
    if session_ids[selected_index] != current_id:
        st.session_state.current_session_id = session_ids[selected_index]
        st.rerun()
        
    st.divider()
    if st.button("🗑️ 删除当前对话"):
        delete_session(current_id)

# ================= 4. 功能函数 (云端版-无代理) =================

def configure_env():
    if not API_KEY: return False
    # 云端不需要代理，直接配置
    genai.configure(api_key=API_KEY)
    return True

def upload_files(uploaded_files):
    """上传文件并返回引用"""
    # 云端文件系统处理
    temp_dir = "cloud_temp"
    if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    
    refs = []
    status_bar = st.progress(0)
    status_text = st.empty()
    
    # 1. 保存并排序
    local_paths = []
    for f in uploaded_files:
        path = os.path.join(temp_dir, f.name)
        with open(path, "wb") as buffer: buffer.write(f.getbuffer())
        local_paths.append(path)
    local_paths.sort()
    
    # 2. 上传
    for i, path in enumerate(local_paths):
        name = os.path.basename(path)
        status_text.text(f"正在上传 {i+1}/{len(local_paths)}: {name}")
        try:
            f = genai.upload_file(path)
            refs.append(f)
        except Exception as e:
            st.error(f"上传失败: {e}")
        status_bar.progress((i+1)/len(local_paths))
    
    # 3. 等待解析
    if refs:
        status_text.text("等待 Google 解析图片...")
        while True:
            ready = True
            for r in refs:
                if genai.get_file(r.name).state.name == "PROCESSING":
                    ready = False; break
            if ready: break
            time.sleep(2)
            
    status_text.empty()
    status_bar.empty()
    shutil.rmtree(temp_dir)
    return refs

# ================= 5. 主界面逻辑 =================

if not configure_env():
    st.warning("⚠️ 未检测到 API Key！请在代码中填入，或在 Streamlit Secrets 中配置。")
    st.stop()

st.header(f"🦁 {current_session['title']}")

# --- 文件上传 ---
# 只在文件还没处理过时显示上传框
if not current_session['files']:
    uploaded_files = st.file_uploader("📂 拖入图片/文档 (支持批量)", accept_multiple_files=True)
    if uploaded_files:
        if st.button("开始上传"):
            refs = upload_files(uploaded_files)
            current_session['files'] = refs
            current_session['processed'] = False
            st.success(f"已挂载 {len(refs)} 个文件")
            st.rerun()
else:
    st.info(f"📚 当前对话已包含 {len(current_session['files'])} 个文件")
    if st.button("清除文件 (重新上传)"):
        current_session['files'] = []
        current_session['processed'] = False
        st.rerun()

# --- 聊天区域 ---
# 恢复聊天对象
try:
    model = genai.GenerativeModel(selected_model)
    # 这里我们不用 start_chat 的 history，而是手动管理，因为要支持多会话切换
    chat = model.start_chat(history=[]) 
except Exception as e:
    st.error(f"模型连接失败: {e}")
    st.stop()

# 显示历史消息
for msg in current_session['history']:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 输入框
if prompt := st.chat_input("输入问题..."):
    # 1. 记录并显示用户提问
    current_session['history'].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # 2. 生成回复
    with st.chat_message("assistant"):
        box = st.empty()
        full_text = ""
        
        try:
            # 构造历史上下文 (为了让 AI 记住之前的对话)
            # 这一步稍微复杂点：我们需要把 session 里的 history 转换成 gemini 的格式
            history_for_api = []
            for h in current_session['history'][:-1]: # 不包含刚发的这句
                history_for_api.append({
                    "role": "user" if h["role"] == "user" else "model",
                    "parts": [h["content"]]
                })
            
            chat.history = history_for_api
            
            # 发送逻辑
            if current_session['files'] and not current_session['processed']:
                # 第一次发带图片
                parts = [prompt] + current_session['files']
                response = chat.send_message(parts, stream=True)
                current_session['processed'] = True
            else:
                # 纯文字
                response = chat.send_message(prompt, stream=True)
                
            for chunk in response:
                full_text += chunk.text
                box.markdown(full_text + "▌")
            box.markdown(full_text)
            
            # 记录回复
            current_session['history'].append({"role": "assistant", "content": full_text})
            
            # (可选) 根据第一句话自动修改会话标题
            if len(current_session['history']) == 2:
                current_session['title'] = prompt[:10] + "..."
                st.rerun()
                
        except Exception as e:
            st.error(f"出错: {e}")
