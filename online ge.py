import streamlit as st
import os
import time
import shutil
import uuid
from google import genai
from google.genai import types

# ================= 0. 版本与配置 =================
APP_VERSION = "v4.3.0-FINAL"
BUILD_DATE = "2026-01-18"

st.set_page_config(page_title=f"凶哥哥的 AI {APP_VERSION}", page_icon="🦁", layout="wide")

# 安全读取 Key
try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    API_KEY = None

# 初始化 Session
if "all_sessions" not in st.session_state:
    default_id = str(uuid.uuid4())
    st.session_state.all_sessions = {
        default_id: {
            "title": "新对话", 
            "history": [], 
            "files_meta": [], 
            "files_processed": False 
        }
    }
    st.session_state.current_session_id = default_id

def get_current_session():
    sid = st.session_state.current_session_id
    return st.session_state.all_sessions.get(sid, list(st.session_state.all_sessions.values())[0])

current_session = get_current_session()

# ================= 1. 侧边栏 =================
with st.sidebar:
    st.title("🦁 凶哥哥的 AI")
    st.caption(f"官方最新 SDK 驱动 | {APP_VERSION}")
    
    with st.expander("⚙️ 核心配置", expanded=True):
        # 仅保留确认可用的高性能模型
        model_list = [
            "gemini-2.5-flash",         # 2026 稳定主力，推荐用于 20 张图片整理
            "gemini-3-flash-preview",   # 2026 最新极速预览版
        ]
        selected_model = st.selectbox("选择模型", model_list, index=0)
        temperature = st.slider("创造力", 0.0, 1.0, 0.2) # 文档分析建议保持低位
        st.info("💡 联网搜索已默认后台开启")

    st.divider()
    if st.button("➕ 新建对话", use_container_width=True):
        nid = str(uuid.uuid4())
        st.session_state.all_sessions[nid] = {"title": "新对话", "history": [], "files_meta": [], "files_processed": False}
        st.session_state.current_session_id = nid; st.rerun()

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
                if st.button("🗑️ 删除", key=f"d_{sid}"):
                    if len(st.session_state.all_sessions) > 1: del st.session_state.all_sessions[sid]; st.rerun()

# ================= 2. 核心功能函数 =================

def safe_upload_handler(client, files):
    """
    极简自动上传：解决编码问题并提供实时反馈
    """
    temp_dir = "cloud_tmp"
    shutil.rmtree(temp_dir, ignore_errors=True); os.makedirs(temp_dir)
    file_metas = []
    
    # 自动处理流程
    with st.status("🛸 AI 正在扫描附件并建立连接...", expanded=True) as status:
        for i, f in enumerate(files):
            # 编码安全：强制重命名
            ext = os.path.splitext(f.name)[1].lower()
            if not ext: ext = ".pdf" if f.type == "application/pdf" else ".jpg"
            safe_name = f"up_{i}{ext}"
            p = os.path.join(temp_dir, safe_name)
            
            with open(p, "wb") as b: b.write(f.getbuffer())
            
            try:
                m_type = "application/pdf" if ext == '.pdf' else "image/jpeg"
                r = client.files.upload(file=p, config={"mime_type": m_type})
                file_metas.append({"uri": r.uri, "mime_type": r.mime_type, "display_name": f.name})
                st.write(f"✔️ {f.name} 解析成功")
            except Exception as e:
                st.error(f"传输中断: {f.name}")
        
        # 轮询 ACTIVE
        while True:
            ready = True
            for meta in file_metas:
                f_id = meta["uri"].split("/")[-1] 
                if client.files.get(name=f_id).state.name == "PROCESSING":
                    ready = False; break
            if ready: break
            time.sleep(1.5)
        status.update(label="✅ 视觉通道已就绪", state="complete", expanded=False)
    
    shutil.rmtree(temp_dir, ignore_errors=True)
    return file_metas

# ================= 3. 主界面对话 =================

client = genai.Client(api_key=API_KEY) if API_KEY else None

if client:
    # 渲染历史
    for m in current_session["history"]:
        with st.chat_message("assistant" if m["role"] == "model" else "user"):
            for part in m["parts"]:
                if "text" in part: st.markdown(part["text"])

    # 底部控制区（全新交互布局）
    chat_prompt = None
    with st.container():
        # --- 附件预览卡片区 ---
        if current_session["files_meta"]:
            with st.container(border=True):
                c_1, c_2 = st.columns([0.85, 0.15])
                with c_1:
                    # 横向显示附件标签
                    st.markdown(" ".join([f"`📎 {f['display_name']}`" for f in current_session["files_meta"]]))
                with c_2:
                    if st.button("🗑️ 清空", use_container_width=True):
                        current_session["files_meta"] = []; current_session["files_processed"] = False; st.rerun()

        # --- 自动上传组件 ---
        new_files = st.file_uploader(
            "Upload", type=['pdf', 'png', 'jpg', 'jpeg'], accept_multiple_files=True, 
            key="v18_up", label_visibility="collapsed"
        )
        
        # 交互逻辑：如果有新文件上传，且当前槽位为空，则自动触发
        if new_files and not current_session["files_meta"]:
            current_session["files_meta"] = safe_upload_handler(client, new_files)
            current_session["files_processed"] = False
            st.rerun()

        chat_prompt = st.chat_input("询问 AI 关于附件的任何问题...")

    # 对话执行
    if chat_prompt:
        user_parts = []
        # 第一轮包含文件
        if current_session["files_meta"] and not current_session["files_processed"]:
            for f in current_session["files_meta"]:
                user_parts.append({"file_uri": f["uri"], "mime_type": f["mime_type"]})
            user_parts.append({"text": f"[系统指令] 用户提供了 {len(current_session['files_meta'])} 份材料。请优先根据附件回答。"})
            current_session["files_processed"] = True
        
        user_parts.append({"text": chat_prompt})
        current_session["history"].append({"role": "user", "parts": user_parts})
        st.rerun()

    if current_session["history"] and current_session["history"][-1]["role"] == "user":
        with st.chat_message("assistant"):
            box = st.empty(); full_text = ""
            try:
                # 转换历史
                history_objs = []
                for h in current_session["history"][:-1]:
                    parts_objs = []
                    for p in h["parts"]:
                        if "text" in p: parts_objs.append(types.Part(text=p["text"]))
                        elif "file_uri" in p: parts_objs.append(types.Part.from_uri(file_uri=p["file_uri"], mime_type=p["mime_type"]))
                    history_objs.append(types.Content(role=h["role"], parts=parts_objs))

                # 当前 Payload
                current_payload = []
                for p in current_session["history"][-1]["parts"]:
                    if "text" in p: current_payload.append(types.Part(text=p["text"]))
                    elif "file_uri" in p: current_payload.append(types.Part.from_uri(file_uri=p["file_uri"], mime_type=p["mime_type"]))

                # 创建 Chat (默认隐形开启联网)
                chat_session = client.chats.create(
                    model=selected_model,
                    history=history_objs,
                    config=types.GenerateContentConfig(
                        system_instruction="你是一个全能文档分析专家。请精准识别用户提供的图片或PDF。严禁说你看不到文件。如有必要，请调用联网搜索补充背景。",
                        temperature=temperature,
                        tools=[types.Tool(google_search=types.GoogleSearch())]
                    )
                )
                
                response = chat_session.send_message_stream(message=current_payload)
                for chunk in response:
                    if chunk.text:
                        full_text += chunk.text; box.markdown(full_text + "▌")
                box.markdown(full_text)
                
                current_session["history"].append({"role": "model", "parts": [{"text": full_text}]})
                if len(current_session["history"]) <= 2:
                    current_session["title"] = chat_prompt[:10]
                st.rerun()
            except Exception as e:
                st.error(f"对话异常: {e}")
                current_session["files_processed"] = False
else:
    st.warning("👈 请在 Secrets 中配置 API Key")
