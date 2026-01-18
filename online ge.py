import streamlit as st
import os
import time
import shutil
import uuid
# 核心：使用 2026 官方最新 SDK
from google import genai
from google.genai import types

# ================= 0. 版本与配置 =================
APP_VERSION = "v5.4.0-CLOUD-MODELS"
st.set_page_config(page_title=f"凶哥哥 AI {APP_VERSION}", page_icon="🦁", layout="wide")

# --- 云端安全读取 Key ---
try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("❌ 未检测到 API Key。请在 Streamlit App Settings -> Secrets 中配置 GOOGLE_API_KEY。")
    st.stop()

# ================= 1. Session 初始化 =================
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
        # 容错：如果当前ID不存在，重置或回退
        if not st.session_state.all_sessions:
             new_id = str(uuid.uuid4())
             st.session_state.all_sessions[new_id] = {"title": "新对话", "history": [], "files_meta": [], "processed": False}
        sid = list(st.session_state.all_sessions.keys())[0]
        st.session_state.current_session_id = sid
    return st.session_state.all_sessions[sid]

current_session = get_current_session()

# ================= 2. 核心功能 (云端直连) =================

def get_client():
    return genai.Client(api_key=API_KEY)

def upload_handler_cloud(client, files):
    """
    云端文件上传逻辑：重命名 -> 上传 -> 轮询状态
    """
    temp_dir = "cloud_upload_tmp"
    if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    
    file_metas = []
    
    with st.status("☁️ 正在同步文件至 Google...", expanded=True) as status:
        for i, f in enumerate(files):
            # 1. 安全重命名 (防止中文编码错误)
            ext = os.path.splitext(f.name)[1].lower()
            if not ext: ext = ".pdf" if f.type == "application/pdf" else ".jpg"
            safe_name = f"up_{int(time.time())}_{i}{ext}"
            p = os.path.join(temp_dir, safe_name)
            
            with open(p, "wb") as b: b.write(f.getbuffer())
            
            try:
                # 2. 识别 MIME
                mime = "application/pdf" if ext == ".pdf" else "image/jpeg"
                if "png" in ext: mime = "image/png"
                
                # 3. 上传
                r = client.files.upload(file=p, config={"mime_type": mime})
                
                file_metas.append({
                    "uri": r.uri, 
                    "mime_type": r.mime_type, 
                    "name": r.name,
                    "display_name": f.name
                })
                st.write(f"✅ 已挂载: {f.name}")
            except Exception as e:
                st.error(f"❌ 上传 {f.name} 失败: {e}")
        
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
                        st.error(f"文件处理失败: {meta['display_name']}")
                except: pass
            if all_active: break
            time.sleep(2)
            
        status.update(label="✅ 文件已就绪", state="complete", expanded=False)
        
    shutil.rmtree(temp_dir)
    return file_metas

# ================= 3. 侧边栏 UI =================
with st.sidebar:
    st.header("🦁 凶哥哥的 AI")
    st.caption(f"Cloud Ver | {APP_VERSION}")
    
    with st.expander("⚙️ 模型配置", expanded=True):
        # 【关键更新】根据您 API 返回的真实列表定制
        model_map = {
            "gemini-2.5-flash": "🏆 2.5 Flash (综合最强/推荐)",
            "gemini-2.5-flash-lite": "⚡ 2.5 Flash Lite (极速/高配额)",
            "gemini-2.5-pro": "🧠 2.5 Pro (深度推理/识图)",
            "gemini-3-flash-preview": "🧪 3.0 Flash (最新预览)",
            "gemini-3-pro-preview": "🚀 3.0 Pro (最强逻辑预览)",
            "gemini-2.0-flash": "🛡️ 2.0 Flash (经典稳定)"
        }
        
        selected_key = st.selectbox(
            "选择模型", 
            options=list(model_map.keys()),
            format_func=lambda x: f"{x.replace('gemini-', '')} | {model_map[x].split('(')[1][:-1]}",
            index=0 # 默认选 2.5-flash
        )
        st.info(f"当前: {model_map[selected_key]}")
        
        temperature = st.slider("创造力", 0.0, 1.0, 0.2)
        enable_search = st.toggle("联网搜索", value=True)

    st.divider()
    
    # 附件管理区
    st.subheader("📁 附件管理")
    up_files = st.file_uploader("添加文件", type=['pdf','png','jpg','jpeg'], accept_multiple_files=True, label_visibility="collapsed")
    
    if up_files:
        current_names = [x['display_name'] for x in current_session["files_meta"]]
        new_files = [f for f in up_files if f.name not in current_names]
        
        if new_files:
            client = get_client()
            if client:
                new_metas = upload_handler_cloud(client, new_files)
                current_session["files_meta"].extend(new_metas)
                current_session["processed"] = False 
                st.rerun()

    if current_session["files_meta"]:
        with st.container(border=True):
            for f in current_session["files_meta"]:
                st.caption(f"📎 {f['display_name']}")
            if st.button("🗑️ 清空附件", use_container_width=True):
                current_session["files_meta"] = []
                current_session["processed"] = False
                st.rerun()
    else:
        st.caption("暂无附件")

    st.divider()
    
    # 会话管理
    c1, c2 = st.columns([4, 1])
    with c1: st.caption("历史会话")
    with c2:
        if st.button("➕"):
            nid = str(uuid.uuid4())
            st.session_state.all_sessions[nid] = {"title": "新对话", "history": [], "files_meta": [], "processed": False}
            st.session_state.current_session_id = nid; st.rerun()

    for sid in list(st.session_state.all_sessions.keys()):
        sess = st.session_state.all_sessions[sid]
        active = (sid == st.session_state.current_session_id)
        if st.button(f"{'🔵' if active else '⚪'} {sess['title']}", key=sid, use_container_width=True):
            st.session_state.current_session_id = sid; st.rerun()

# ================= 4. 主聊天界面 =================

client = get_client()

# 1. 渲染历史
for msg in current_session["history"]:
    with st.chat_message("assistant" if msg["role"] == "model" else "user"):
        for part in msg["parts"]:
            if "text" in part: st.markdown(part["text"])
            if "file_uri" in part: st.caption("📄 [附件已发送]")

# 2. 输入框
prompt = st.chat_input("输入问题...")

# 3. 发送逻辑
if prompt and client:
    # --- A. 构造 User Content ---
    user_parts_storage = []
    user_parts_api = []
    
    # 挂载附件 (仅首轮或有新文件)
    if current_session["files_meta"] and not current_session["processed"]:
        sys_hint = "请基于以下附件内容回答："
        user_parts_storage.append({"text": sys_hint})
        user_parts_api.append(types.Part.from_text(text=sys_hint))
        
        for f in current_session["files_meta"]:
            user_parts_storage.append({"file_uri": f["uri"], "mime_type": f["mime_type"]})
            user_parts_api.append(types.Part.from_uri(file_uri=f["uri"], mime_type=f["mime_type"]))
        
        current_session["processed"] = True

    # 加入文本
    user_parts_storage.append({"text": prompt})
    user_parts_api.append(types.Part.from_text(text=prompt))
    
    current_session["history"].append({"role": "user", "parts": user_parts_storage})
    
    # --- B. 构造 History ---
    api_history = []
    for h in current_session["history"][:-1]:
        parts_list = []
        for p in h["parts"]:
            if "text" in p:
                parts_list.append(types.Part.from_text(text=p["text"]))
            elif "file_uri" in p:
                parts_list.append(types.Part.from_uri(file_uri=p["file_uri"], mime_type=p["mime_type"]))
        api_history.append(types.Content(role=h["role"], parts=parts_list))

    # --- C. 调用 API ---
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
            if "404" in err_msg:
                st.error("❌ 模型不可用：该模型在您的区域未开放，请切换到 2.5-Flash 试试。")
            elif "429" in err_msg:
                st.error("❌ 配额超限：请稍等或切换到 Flash-Lite 模型。")
            else:
                st.error(f"出错: {err_msg}")
