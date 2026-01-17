import streamlit as st
import os
import time
import shutil
import uuid
# 核心：使用 google-genai 最新 SDK
from google import genai
from google.genai import types

# ================= 0. 版本元数据 =================
APP_VERSION = "v4.0.6-PRO"
BUILD_DATE = "2026-01-17"

# ================= 1. 页面初始化 =================
st.set_page_config(
    page_title=f"凶哥哥的 AI {APP_VERSION}", 
    page_icon="🦁", 
    layout="wide"
)

# 安全读取 Secrets 里的 API KEY
try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    API_KEY = None

# 初始化 Session State (关键：统一存储为符合 API 规范的 Content 结构)
if "all_sessions" not in st.session_state:
    default_id = str(uuid.uuid4())
    st.session_state.all_sessions = {
        default_id: {
            "title": "新对话", 
            "history": [], # 存储结构：types.Content 对象列表
            "files": [],   # 存储已上传的 File 引用
            "processed": False 
        }
    }
    st.session_state.current_session_id = default_id

def get_current_session():
    sid = st.session_state.current_session_id
    return st.session_state.all_sessions.get(sid, list(st.session_state.all_sessions.values())[0])

current_session = get_current_session()

# ================= 2. 侧边栏 =================
with st.sidebar:
    st.title("🦁 凶哥哥的 AI")
    st.caption(f"版本: {APP_VERSION} | SDK: {genai.__version__}")
    
    with st.expander("⚙️ 模型设置", expanded=True):
        # 根据反馈，移除 1.5 Pro，首选 2.0 Flash
        model_list = [
            "gemini-2.0-flash",         # 2026 旗舰：识图+搜索
            "gemini-2.0-flash-lite-preview-02-05", 
            "gemini-1.5-flash",         # 备选稳定版
        ]
        selected_model = st.selectbox("选择模型", model_list, index=0)
        temperature = st.slider("创造力", 0.0, 2.0, 0.1) # 识图务必调低
        enable_search = st.toggle("🌍 联网搜索", value=True)

    st.divider()
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

# ================= 3. 核心功能函数 =================

def get_client():
    if not API_KEY:
        st.error("❌ 未检测到 API KEY。请在 Secrets 中配置 GOOGLE_API_KEY。")
        return None
    return genai.Client(api_key=API_KEY)

def upload_to_gemini(client, files):
    """按照官方 SDK 规范上传并检查状态"""
    temp_dir = "cloud_tmp"
    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir)
    
    uploaded_refs = []
    with st.status("🚀 正在将附件送往 Google 服务器...", expanded=True) as status:
        # 1. 物理保存与排序
        local_files = []
        for f in files:
            p = os.path.join(temp_dir, f.name)
            with open(p, "wb") as b: b.write(f.getbuffer())
            local_files.append(p)
        local_files.sort()

        # 2. 调用 SDK 上传
        for path in local_files:
            try:
                # 显式指定 mime_type
                m_type = "application/pdf" if path.lower().endswith(".pdf") else "image/jpeg"
                r = client.files.upload(path=path, config={"mime_type": m_type})
                uploaded_refs.append(r)
                st.write(f"✅ 已上传: {os.path.basename(path)}")
            except Exception as e: st.error(f"上传出错: {e}")
        
        # 3. 轮询状态直到 ACTIVE
        st.write("📖 AI 正在进行视觉预处理...")
        while True:
            all_ready = True
            for r in uploaded_refs:
                f_info = client.files.get(name=r.name)
                if f_info.state.name == "PROCESSING":
                    all_ready = False; break
            if all_ready: break
            time.sleep(2)
        status.update(label="✅ 附件解析完成，AI 现在可以‘看见’它们了", state="complete", expanded=False)
    
    shutil.rmtree(temp_dir, ignore_errors=True)
    return uploaded_refs

# ================= 4. 主对话逻辑 =================

client = get_client()
if client:
    # --- 1. 渲染历史记录 (官方规范渲染) ---
    for m in current_session["history"]:
        with st.chat_message("assistant" if m.role == "model" else "user"):
            for part in m.parts:
                if part.text: st.markdown(part.text)
                # 历史中的图片不重复渲染，保持界面干净

    # --- 2. 底部控制区 ---
    chat_prompt = None
    with st.container():
        # 显示当前挂载的文件
        if current_session["files"]:
            st.success(f"📎 附件已就绪 ({len(current_session['files'])} 个)。AI 已获授权读取。")
            if st.button("🗑️ 清理所有附件"):
                current_session["files"] = []; current_session["processed"] = False; st.rerun()

        # 上传区：一个组件搞定 Browse 和 Drag
        uploaded_files = st.file_uploader(
            "在此拖入材料或点击上传 (PDF/图片)", 
            accept_multiple_files=True, 
            key="v6_uploader",
            label_visibility="collapsed"
        )
        
        if uploaded_files and not current_session["files"]:
            if st.button("🚀 激活附件分析权限", use_container_width=True, type="primary"):
                current_session["files"] = upload_to_gemini(client, uploaded_files)
                current_session["processed"] = False
                st.rerun()

        chat_prompt = st.chat_input("现在可以针对附件提问了...")

    # --- 3. 发送逻辑 (核心重构) ---
    if chat_prompt:
        # 用户输入的文字转为 Part 存入历史
        user_content = types.Content(role="user", parts=[types.Part(text=chat_prompt)])
        current_session["history"].append(user_content)
        st.rerun()

    if current_session["history"] and current_session["history"][-1].role == "user":
        with st.chat_message("assistant"):
            box = st.empty(); full_text = ""
            
            # --- 构造本次发送的内容 (Payload) ---
            current_payload_parts = []
            
            # 只有在第一轮（processed=False）时，显式将文件 Part 塞进当前消息
            if current_session["files"] and not current_session["processed"]:
                # 注入最高优先级的视觉指引
                current_payload_parts.append(types.Part(text="[Vision System Active] The user has provided the following documents/images. Please analyze them thoroughly and respond to the user's query based on these visuals."))
                for f_ref in current_session["files"]:
                    # 正确构造文件引用 Part
                    current_payload_parts.append(types.Part.from_uri(file_uri=f_ref.uri, mime_type=f_ref.mime_type))
            
            # 加入用户的问题 Part
            current_payload_parts.extend(current_session["history"][-1].parts)

            try:
                # 配置工具
                tools = [types.Tool(google_search=types.GoogleSearch())] if enable_search else []

                # 创建 Chat (注意：history 必须是 types.Content 列表)
                chat_session = client.chats.create(
                    model=selected_model,
                    history=current_session["history"][:-1], # 传入之前的历史
                    config=types.GenerateContentConfig(
                        system_instruction="你是一个拥有视觉能力的文档专家。请优先根据用户上传的附件（图片或PDF）进行精准回答。严禁回答'我看不到文件'。",
                        temperature=temperature,
                        tools=tools
                    )
                )
                
                # 开始生成
                response = chat_session.send_message_stream(message=current_payload_parts)
                for chunk in response:
                    if chunk.text:
                        full_text += chunk.text
                        box.markdown(full_text + "▌")
                
                box.markdown(full_text)
                
                # 成功后：
                current_session["processed"] = True 
                # 将 AI 的回复存入历史
                model_content = types.Content(role="model", parts=[types.Part(text=full_text)])
                current_session["history"].append(model_content)
                
                # 自动标题
                if len(current_session["history"]) <= 2:
                    current_session["title"] = chat_prompt[:10]
                st.rerun()

            except Exception as e:
                st.error(f"对话异常: {e}")
