import streamlit as st
import os
import time
import shutil
import uuid
# 核心：使用 2026 最新版 SDK
from google import genai
from google.genai import types

# ================= 0. 配置与版本 =================
APP_VERSION = "v5.1.0-LOCAL"
st.set_page_config(page_title=f"凶哥哥 AI {APP_VERSION}", page_icon="🦁", layout="wide")

# 初始化 Session
if "all_sessions" not in st.session_state:
    default_id = str(uuid.uuid4())
    st.session_state.all_sessions = {
        default_id: {
            "title": "新对话",
            "history": [], 
            "files_meta": [], 
            "processed": False
        }
    }
    st.session_state.current_session_id = default_id

def get_current_session():
    sid = st.session_state.current_session_id
    if sid not in st.session_state.all_sessions:
        sid = list(st.session_state.all_sessions.keys())[0]
        st.session_state.current_session_id = sid
    return st.session_state.all_sessions[sid]

current_session = get_current_session()

# ================= 1. 侧边栏 (含代理设置) =================
with st.sidebar:
    st.header("🦁 凶哥哥的 AI")
    st.caption(f"本地代理版 | SDK: {genai.__version__}")
    
    # --- 🔌 网络与密钥设置 (中国大陆专用) ---
    with st.expander("🔌 连接设置", expanded=True):
        # 1. API Key 输入框 (本地通常没有 Secrets)
        api_key_input = st.text_input("API Key", type="password", placeholder="AIzaSy...")
        
        # 2. 代理设置 (关键！)
        use_proxy = st.checkbox("开启本地代理", value=True)
        proxy_port = st.text_input("代理端口", value="1080", disabled=not use_proxy, help="Clash通常是7890，v2rayN通常是10809")

    # --- 模型配置 ---
    with st.expander("⚙️ 模型参数", expanded=True):
        model_list = [
            "gemini-2.5-flash-lite",  # 速度最快，配额10RPM
            "gemini-2.5-flash",       # 平衡主力
            "gemini-2.0-flash",       # 经典稳定
        ]
        selected_model = st.selectbox("选择模型", model_list, index=0)
        temperature = st.slider("创造力", 0.0, 1.0, 0.2)
        enable_search = st.toggle("联网搜索", value=True)

    st.divider()
    
    # 附件管理区
    st.subheader("📁 附件管理")
    up_files = st.file_uploader("添加文件", type=['pdf','png','jpg','jpeg'], accept_multiple_files=True, label_visibility="collapsed")
    
    # 自动上传逻辑 (复用 Client)
    if up_files:
        # 获取 Client (带代理配置)
        if api_key_input:
            # 临时配置代理环境变量
            if use_proxy and proxy_port:
                os.environ['HTTP_PROXY'] = f"http://127.0.0.1:{proxy_port}"
                os.environ['HTTPS_PROXY'] = f"http://127.0.0.1:{proxy_port}"
            else:
                os.environ.pop('HTTP_PROXY', None); os.environ.pop('HTTPS_PROXY', None)
            
            client_tmp = genai.Client(api_key=api_key_input)
            
            # 检查去重
            current_names = [x['display_name'] for x in current_session["files_meta"]]
            new_files_obj = [f for f in up_files if f.name not in current_names]
            
            if new_files_obj:
                # 引用下面的上传函数
                # (由于 Streamlit 执行顺序，这里我们临时内联一个简化版上传逻辑或在下面定义)
                pass 

    # 历史列表
    st.caption("💬 历史会话")
    if st.button("➕ 新建对话", use_container_width=True):
        nid = str(uuid.uuid4())
        st.session_state.all_sessions[nid] = {"title": "新对话", "history": [], "files_meta": [], "processed": False}
        st.session_state.current_session_id = nid; st.rerun()
        
    for sid in list(st.session_state.all_sessions.keys()):
        sess = st.session_state.all_sessions[sid]
        active = (sid == st.session_state.current_session_id)
        if st.button(f"{'🔵' if active else '⚪'} {sess['title']}", key=sid, use_container_width=True):
            st.session_state.current_session_id = sid; st.rerun()

# ================= 2. 核心功能函数 =================

def get_client():
    if not api_key_input:
        st.warning("👈 请在左侧填入 API Key")
        return None
    
    # 【关键】根据侧边栏设置配置代理
    if use_proxy and proxy_port:
        # 设置环境变量，httpx (SDK底层) 会自动读取
        os.environ['HTTP_PROXY'] = f"http://127.0.0.1:{proxy_port}"
        os.environ['HTTPS_PROXY'] = f"http://127.0.0.1:{proxy_port}"
    else:
        # 清除环境变量，防止干扰
        os.environ.pop('HTTP_PROXY', None)
        os.environ.pop('HTTPS_PROXY', None)
    
    return genai.Client(api_key=api_key_input)

def upload_handler_local(client, files):
    """
    本地上传逻辑 (兼容中文名处理)
    """
    temp_dir = "temp_upload"
    if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    
    file_metas = []
    
    with st.status("📡 正在通过代理上传至 Google...", expanded=True) as status:
        for i, f in enumerate(files):
            # 1. 本地重命名 (防止 Windows 中文路径乱码)
            ext = os.path.splitext(f.name)[1].lower()
            if not ext: ext = ".pdf" if f.type == "application/pdf" else ".jpg"
            safe_name = f"doc_{int(time.time())}_{i}{ext}"
            local_path = os.path.join(temp_dir, safe_name)
            
            with open(local_path, "wb") as b: b.write(f.getbuffer())
            
            try:
                # 2. 识别 MIME
                mime = "application/pdf" if ext == ".pdf" else "image/jpeg"
                if "png" in ext: mime = "image/png"
                
                # 3. 上传 (使用 file= 参数)
                r = client.files.upload(file=local_path, config={"mime_type": mime})
                
                file_metas.append({
                    "uri": r.uri, 
                    "mime_type": r.mime_type, 
                    "name": r.name,
                    "display_name": f.name
                })
                st.write(f"✅ 已挂载: {f.name}")
            except Exception as e:
                st.error(f"❌ 上传 {f.name} 失败: {e}")
                st.caption("提示：请检查代理端口是否正确 (Clash=7890, v2rayN=10809)")
        
        # 4. 状态轮询
        st.write("⏳ 等待 Google 视觉引擎索引...")
        while True:
            all_active = True
            for meta in file_metas:
                try:
                    f_info = client.files.get(name=meta["name"])
                    if f_info.state.name == "PROCESSING":
                        all_active = False; break
                    elif f_info.state.name == "FAILED":
                        st.error(f"处理失败: {meta['display_name']}")
                except:
                    pass # 忽略网络波动
            if all_active: break
            time.sleep(2)
            
        status.update(label="✅ 文件已就绪", state="complete", expanded=False)
        
    shutil.rmtree(temp_dir)
    return file_metas

# ================= 3. 主界面逻辑 =================

# 补全侧边栏的上传触发逻辑
if up_files and not current_session.get("upload_triggered", False):
    # 检查新文件
    current_display_names = [x['display_name'] for x in current_session["files_meta"]]
    new_files = [f for f in up_files if f.name not in current_display_names]
    
    if new_files:
        client = get_client()
        if client:
            new_metas = upload_handler_local(client, new_files)
            current_session["files_meta"].extend(new_metas)
            current_session["processed"] = False
            current_session["upload_triggered"] = True # 防止刷新重复触发
            st.rerun()

# 附件展示区
if current_session["files_meta"]:
    with st.sidebar.container(border=True):
        for f in current_session["files_meta"]:
            st.text(f"📄 {f['display_name']}")
        if st.button("🗑️ 清空所有", use_container_width=True):
            current_session["files_meta"] = []
            current_session["processed"] = False
            st.rerun()

client = get_client()

# 1. 渲染历史
for msg in current_session["history"]:
    with st.chat_message("assistant" if msg["role"] == "model" else "user"):
        st.markdown(msg["content"])

# 2. 输入框
prompt = st.chat_input("输入问题...")

# 3. 发送逻辑
if prompt and client:
    # 存用户输入
    current_session["history"].append({"role": "user", "content": prompt})
    
    with st.chat_message("assistant"):
        box = st.empty()
        full_text = ""
        
        try:
            # --- 历史构建 ---
            api_history = []
            for h in current_session["history"][:-1]: 
                api_history.append(types.Content(
                    role=h["role"],
                    parts=[types.Part.from_text(text=h["content"])]
                ))

            # --- Payload 构建 ---
            current_parts = []
            
            # 挂载文件 (仅首轮或未处理时)
            if current_session["files_meta"]:
                if not current_session["processed"]:
                    current_parts.append(types.Part.from_text(text="[System: Please analyze these files]"))
                
                for f in current_session["files_meta"]:
                    current_parts.append(types.Part.from_uri(
                        file_uri=f["uri"],
                        mime_type=f["mime_type"]
                    ))
                current_session["processed"] = True

            current_parts.append(types.Part.from_text(text=prompt))

            # --- 工具配置 ---
            tools_cfg = [types.Tool(google_search=types.GoogleSearch())] if enable_search else None

            # --- 发送请求 ---
            chat = client.chats.create(
                model=selected_model,
                history=api_history,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    tools=tools_cfg,
                    system_instruction="你是一个全能助手。"
                )
            )
            
            response = chat.send_message_stream(message=current_parts)
            
            for chunk in response:
                if chunk.text:
                    full_text += chunk.text
                    box.markdown(full_text + "▌")
            
            box.markdown(full_text)
            current_session["history"].append({"role": "model", "content": full_text})
            
            if len(current_session["history"]) == 2:
                current_session["title"] = prompt[:10]
            st.rerun()

        except Exception as e:
            st.error(f"发生错误: {e}")
            st.caption("提示: 如果是 ConnectTimeout，请检查左侧代理端口是否正确 (v2rayN=10809)")
