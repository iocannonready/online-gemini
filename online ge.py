import streamlit as st
import os
import time
import shutil
import google.generativeai as genai
import uuid
from google.api_core import exceptions

# ================= 1. 配置区域 =================

# 你的 API Key (如果 Streamlit Secrets 没填，就会用这个)
HARDCODED_KEY = "" 

# 尝试获取 Key
try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    API_KEY = HARDCODED_KEY

# 页面配置
st.set_page_config(
    page_title="凶哥哥的AI",
    page_icon="🦁",
    layout="wide"
)

# ================= 2. 会话管理 & 状态初始化 =================

if "all_sessions" not in st.session_state:
    default_id = str(uuid.uuid4())
    st.session_state.all_sessions = {
        default_id: {
            "title": "新对话 1", 
            "history": [], 
            "files": [], 
            "processed": False 
        }
    }
    st.session_state.current_session_id = default_id

# 自动重发标记 (用于重新生成功能)
if "trigger_regenerate" not in st.session_state:
    st.session_state.trigger_regenerate = False

def create_new_session():
    new_id = str(uuid.uuid4())
    count = len(st.session_state.all_sessions) + 1
    st.session_state.all_sessions[new_id] = {
        "title": f"新对话 {count}",
        "history": [], # 结构: {"role":Str, "content":Str, "usage":Str}
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

# 获取当前会话
current_id = st.session_state.current_session_id
current_session = st.session_state.all_sessions[current_id]

# ================= 3. 侧边栏 (高级控制) =================
with st.sidebar:
    st.title("🦁 凶哥哥的AI")
    
    # --- 模型与参数 ---
    with st.expander("🧠 模型与参数", expanded=True):
        selected_model = st.selectbox(
            "模型选择", 
            ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"],
            index=0
        )
        
        # 创造力调节 (Temperature)
        temperature = st.slider(
            "创造力 (Temperature)", 
            min_value=0.0, max_value=2.0, value=0.7, step=0.1,
            help="数值越高越发散创意，数值越低越严谨。"
        )
        
        # 联网开关
        enable_search = st.toggle("🌍 联网搜索 (Google Grounding)", value=False, help="开启后，AI 会查询最新实时信息。")

    # --- 人设指令 ---
    with st.expander("🎭 系统人设 (System Prompt)", expanded=False):
        system_instruction = st.text_area(
            "你希望 AI 扮演什么角色？",
            placeholder="例如：你是一位资深律师，请用专业且严谨的口吻回答问题。",
            height=100
        )

    st.divider()
    
    # --- 对话列表 ---
    col1, col2 = st.columns([4, 1])
    with col1:
        st.caption("💬 对话列表")
    with col2:
        if st.button("➕", help="新建对话"):
            create_new_session()
    
    session_ids = list(st.session_state.all_sessions.keys())
    session_titles = [st.session_state.all_sessions[k]["title"] for k in session_ids]
    
    current_index = session_ids.index(current_id) if current_id in session_ids else 0
    
    selected_index = st.radio(
        "History", range(len(session_ids)), 
        format_func=lambda i: session_titles[i],
        index=current_index, label_visibility="collapsed"
    )
    
    if session_ids[selected_index] != current_id:
        st.session_state.current_session_id = session_ids[selected_index]
        st.rerun()
    
    # 重命名
    with st.popover("🖊️ 重命名"):
        new_name = st.text_input("新名称", value=current_session['title'])
        if new_name != current_session['title']:
            current_session['title'] = new_name
            st.rerun()
            
    if st.button("🗑️ 删除此对话", use_container_width=True):
        delete_session(current_id)

# ================= 4. 核心功能函数 =================

def configure_env():
    if not API_KEY: return False
    genai.configure(api_key=API_KEY)
    return True

def upload_files(uploaded_files):
    temp_dir = "cloud_temp"
    if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    
    refs = []
    status_text = st.empty()
    
    local_paths = []
    for f in uploaded_files:
        path = os.path.join(temp_dir, f.name)
        with open(path, "wb") as buffer: buffer.write(f.getbuffer())
        local_paths.append(path)
    local_paths.sort()
    
    for i, path in enumerate(local_paths):
        name = os.path.basename(path)
        status_text.caption(f"📤 正在上传 {i+1}/{len(local_paths)}: {name}")
        try:
            f = genai.upload_file(path)
            refs.append(f)
        except Exception as e:
            st.error(f"上传失败: {e}")
    
    if refs:
        status_text.caption("⏳ 正在等待 Google 解析文档...")
        while True:
            ready = True
            for r in refs:
                if genai.get_file(r.name).state.name == "PROCESSING":
                    ready = False; break
            if ready: break
            time.sleep(1)
            
    status_text.empty()
    shutil.rmtree(temp_dir)
    return refs

# ================= 5. 主界面逻辑 =================

if not configure_env():
    st.warning("⚠️ 请配置 API Key")
    st.stop()

# 极简标题
st.markdown(f"##### 🗨️ {current_session['title']}")

# --- 1. 初始化模型 (动态配置) ---
try:
    # 配置联网工具
    tools = []
    if enable_search:
        tools = [{"google_search": {}}] # 启用 Google 搜索

    generation_config = {
        "temperature": temperature,
        # "max_output_tokens": 8192, 
    }
    
    model = genai.GenerativeModel(
        selected_model,
        generation_config=generation_config,
        system_instruction=system_instruction if system_instruction else None, # 注入人设
        tools=tools
    )
    chat = model.start_chat(history=[])
except Exception as e:
    st.error(f"模型配置失败: {e}")
    st.stop()

# --- 2. 显示历史消息 ---
for msg in current_session['history']:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        # 显示 Token 统计 (如果有)
        if "usage" in msg:
            st.caption(f"📊 {msg['usage']}")

# --- 3. 重新生成按钮 (位于对话流底部) ---
if len(current_session['history']) >= 2:
    last_role = current_session['history'][-1]['role']
    if last_role == 'assistant':
        col_regen, col_space = st.columns([1, 6])
        with col_regen:
            if st.button("🔄 重新生成", help="删除上一条回复并重试"):
                # 逻辑：删除最后一条 Assistant 回复，并触发自动发送
                current_session['history'].pop() 
                st.session_state.trigger_regenerate = True
                st.rerun()

# --- 4. 附件按钮 (Popover) ---
with st.popover("📎 添加图片/文档", use_container_width=True):
    if current_session['files']:
        st.info(f"✅ 已挂载 {len(current_session['files'])} 个文件")
        if st.button("清空文件"):
            current_session['files'] = []
            current_session['processed'] = False
            st.rerun()
    
    uploaded_files = st.file_uploader("拖拽文件", accept_multiple_files=True, label_visibility="collapsed")
    if uploaded_files:
        if st.button("确认上传"):
            refs = upload_files(uploaded_files)
            current_session['files'] = refs
            current_session['processed'] = False
            st.success("上传成功")
            time.sleep(0.5)
            st.rerun()

# --- 5. 处理输入 (包含重新生成逻辑) ---

# 获取输入：或者是用户打字的，或者是“重新生成”触发的
prompt = st.chat_input("在此输入问题...")

if st.session_state.trigger_regenerate:
    # 如果是重新生成，从历史记录里找回用户最后一条话
    if current_session['history'] and current_session['history'][-1]['role'] == 'user':
        prompt = current_session['history'][-1]['content']
        # 临时移除这一条，因为下面代码会再次 append
        current_session['history'].pop() 
    st.session_state.trigger_regenerate = False # 重置标记

if prompt:
    # 显示用户输入
    current_session['history'].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # 生成回复
    with st.chat_message("assistant"):
        box = st.empty()
        full_text = ""
        usage_info = ""
        
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
                parts = [prompt] + current_session['files']
                response = chat.send_message(parts, stream=True)
                current_session['processed'] = True
            else:
                response = chat.send_message(prompt, stream=True)
            
            # 流式接收
            for chunk in response:
                full_text += chunk.text
                box.markdown(full_text + "▌")
                # 尝试获取 Token 统计
                if chunk.usage_metadata:
                    in_tok = chunk.usage_metadata.prompt_token_count
                    out_tok = chunk.usage_metadata.candidates_token_count
                    usage_info = f"Token: 输入 {in_tok} + 输出 {out_tok} = 总计 {in_tok + out_tok}"

            box.markdown(full_text)
            
            # 保存记录
            msg_record = {"role": "assistant", "content": full_text}
            if usage_info:
                msg_record["usage"] = usage_info
                st.caption(f"📊 {usage_info}")
                
            current_session['history'].append(msg_record)
            
            # 自动改名
            if len(current_session['history']) == 2:
                current_session['title'] = prompt[:8] + "..."
                st.rerun()
                
        except Exception as e:
            st.error(f"Error: {e}")
