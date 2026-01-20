import streamlit as st
import os
import time
import shutil
import uuid
import json
# 核心：使用 2026 官方最新 SDK
from google import genai
from google.genai import types

# ================= 0. 版本与配置 =================
APP_VERSION = "v5.6.0-CLOUD-PURE"
st.set_page_config(page_title=f"凶哥哥 AI {APP_VERSION}", page_icon="🦁", layout="wide")

# 安全读取 Key
try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("❌ 未检测到 API Key。请在 Secrets 中配置。")
    st.stop()

# ================= 1. 数据结构初始化 =================
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
        if not st.session_state.all_sessions:
             new_id = str(uuid.uuid4())
             st.session_state.all_sessions[new_id] = {"title": "新对话", "history": [], "files_meta": [], "processed": False}
        sid = list(st.session_state.all_sessions.keys())[0]
        st.session_state.current_session_id = sid
    return st.session_state.all_sessions[sid]

current_session = get_current_session()

# ================= 2. 核心功能函数 =================

def get_client():
    # 【关键修正】云端版本严禁设置 HTTP_PROXY，直接初始化
    # 如果之前设置过环境变量，这里强制清除，防止报错
    os.environ.pop('HTTP_PROXY', None)
    os.environ.pop('HTTPS_PROXY', None)
    return genai.Client(api_key=API_KEY)

def upload_handler_cloud(client, files):
    temp_dir = "cloud_upload_tmp"
    if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    file_metas = []
    
    with st.status("☁️ 正在同步文件至 Google...", expanded=True) as status:
        for i, f in enumerate(files):
            ext = os.path.splitext(f.name)[1].lower()
            if not ext: ext = ".pdf" if f.type == "application/pdf" else ".jpg"
            safe_name = f"up_{int(time.time())}_{i}{ext}"
            p = os.path.join(temp_dir, safe_name)
            
            with open(p, "wb") as b: b.write(f.getbuffer())
            try:
                mime = "application/pdf" if ext == ".pdf" else "image/jpeg"
                if "png" in ext: mime = "image/png"
                r = client.files.upload(file=p, config={"mime_type": mime})
                file_metas.append({"uri": r.uri, "mime_type": r.mime_type, "name": r.name, "display_name": f.name})
                st.write(f"✅ 已挂载: {f.name}")
            except Exception as e:
                st.error(f"❌ 上传 {f.name} 失败: {e}")
        
        st.write("⏳ 等待索引生效...")
        while True:
            all_active = True
            for meta in file_metas:
                try:
                    if client.files.get(name=meta["name"]).state.name == "PROCESSING":
                        all_active = False; break
                except: pass
            if all_active: break
            time.sleep(1)
        status.update(label="✅ 文件已就绪", state="complete", expanded=False)
        
    shutil.rmtree(temp_dir)
    return file_metas

# ================= 3. 侧边栏 =================
with st.sidebar:
    st.header("🦁 凶哥哥的 AI")
    st.caption(f"Cloud Ver | {APP_VERSION}")

    # 模块 A: 会话管理
    st.markdown("### 💬 会话管理")
    if st.button("➕ 新建对话", use_container_width=True):
        nid = str(uuid.uuid4())
        st.session_state.all_sessions[nid] = {"title": "新对话", "history": [], "files_meta": [], "processed": False}
        st.session_state.current_session_id = nid; st.rerun()

    session_keys = list(st.session_state.all_sessions.keys())
    for sid in session_keys:
        sess = st.session_state.all_sessions[sid]
        active = (sid == st.session_state.current_session_id)
        col1, col2 = st.columns([0.85, 0.15])
        with col1:
            if st.button(f"{'📂' if active else '⚪'} {sess['title']}", key=f"btn_{sid}", use_container_width=True, type="primary" if active else "secondary"):
                st.session_state.current_session_id = sid; st.rerun()
        with col2:
            with st.popover("⋮", use_container_width=True):
                new_title = st.text_input("重命名", value=sess["title"], key=f"rename_{sid}")
                if new_title != sess["title"]:
                    sess["title"] = new_title; st.rerun()
                if st.button("🗑️ 删除", key=f"del_{sid}", type="primary"):
                    del st.session_state.all_sessions[sid]; st.rerun()
    
    st.divider()

    # 模块 B: 附件管理
    st.markdown("### 📁 附件管理")
    up_files = st.file_uploader("添加文件 (PDF/图片)", type=['pdf','png','jpg','jpeg'], accept_multiple_files=True, label_visibility="collapsed")
    
    if up_files:
        current_names = [x['display_name'] for x in current_session["files_meta"]]
        new_files = [f for f in up_files if f.name not in current_names]
        if new_files:
            client = get_client()
            new_metas = upload_handler_cloud(client, new_files)
            current_session["files_meta"].extend(new_metas)
            current_session["processed"] = False 
            st.rerun()

    if current_session["files_meta"]:
        with st.container(border=True):
            for f in current_session["files_meta"]:
                st.caption(f"📎 {f['display_name']}")
            if st.button("🗑️ 清空当前附件", use_container_width=True):
                current_session["files_meta"] = []; current_session["processed"] = False; st.rerun()
    else:
        st.info("当前无附件")

    st.divider()

    # 模块 C: 模型配置
    with st.expander("⚙️ 模型配置", expanded=False):
        model_map = {
            "gemini-2.5-flash-lite": "⚡ 2.5 Lite (极速/10RPM)",
            "gemini-2.5-flash": "🏆 2.5 Flash (综合推荐)",
            "gemini-2.0-flash": "🛡️ 2.0 Flash (经典)",
            "gemini-3-flash-preview": "🧪 3.0 Preview (尝鲜)"
        }
        selected_key = st.selectbox("选择模型", options=list(model_map.keys()), format_func=lambda x: f"{x.replace('gemini-', '')}", index=0)
        st.caption(model_map[selected_key])
        temperature = st.slider("创造力", 0.0, 1.0, 0.2)
        enable_search = st.toggle("联网搜索", value=True)

# ================= 4. 主聊天界面 =================

client = get_client()

# 1. 历史记录渲染区
for msg in current_session["history"]:
    with st.chat_message("assistant" if msg["role"] == "model" else "user"):
        for part in msg["parts"]:
            if "text" in part: st.markdown(part["text"])
            if "file_uri" in part: st.caption("📄 [附件已发送]")

# 2. 输入框
prompt = st.chat_input("输入问题...")

# 3. 发送逻辑
if prompt and client:
    # A. 构造 User Content
    user_parts_storage = []
    user_parts_api = []
    
    if current_session["files_meta"] and not current_session["processed"]:
        sys_hint = "请基于以下附件内容回答："
        user_parts_storage.append({"text": sys_hint})
        user_parts_api.append(types.Part.from_text(text=sys_hint))
        
        for f in current_session["files_meta"]:
            user_parts_storage.append({"file_uri": f["uri"], "mime_type": f["mime_type"]})
            user_parts_api.append(types.Part.from_uri(file_uri=f["uri"], mime_type=f["mime_type"]))
        
        current_session["processed"] = True

    user_parts_storage.append({"text": prompt})
    user_parts_api.append(types.Part.from_text(text=prompt))
    
    current_session["history"].append({"role": "user", "parts": user_parts_storage})
    
    # B. 构造 History
    api_history = []
    for h in current_session["history"][:-1]:
        parts_list = []
        for p in h["parts"]:
            if "text" in p:
                parts_list.append(types.Part.from_text(text=p["text"]))
            elif "file_uri" in p:
                parts_list.append(types.Part.from_uri(file_uri=p["file_uri"], mime_type=p["mime_type"]))
        api_history.append(types.Content(role=h["role"], parts=parts_list))

    # C. 调用 API
    with st.chat_message("assistant"):
        box = st.empty()
        full_response = ""
        
        try:
            tools_cfg = [types.Tool(google_search=types.GoogleSearch())] if enable_search else None
            
            chat = client.chats.create(
                model=selected_key,
                history=api_history,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    tools=tools_cfg,
                    system_instruction="你是一个全能助手。如果用户提供了文件，请务必基于文件内容回答。"
                )
            )
            
            response_stream = chat.send_message_stream(message=user_parts_api)
            
            for chunk in response_stream:
                if chunk.text:
                    full_response += chunk.text
                    box.markdown(full_response + "▌")
            
            box.markdown(full_response)
            current_session["history"].append({"role": "model", "parts": [{"text": full_response}]})
            
            if len(current_session["history"]) == 2:
                current_session["title"] = prompt[:10]
            st.rerun()
            
        except Exception as e:
            err_msg = str(e)
            if "111" in err_msg or "Connection refused" in err_msg:
                st.error("❌ 连接错误：云端环境不应使用代理。代码已自动清除代理设置，请重试。")
            elif "404" in err_msg:
                st.error("❌ 模型不可用：请切换模型。")
            elif "429" in err_msg:
                st.error("❌ 配额超限：请切换到 Lite 模型。")
            else:
                st.error(f"出错: {err_msg}")
