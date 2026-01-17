import streamlit as st
import os
import time
import shutil
import uuid
# 核心：使用 2026 官方最新 SDK
from google import genai
from google.genai import types

# ================= 0. 版本元数据 =================
APP_VERSION = "v4.0.8-PRO"
BUILD_DATE = "2026-01-17"

# ================= 1. 页面初始化 =================
st.set_page_config(
    page_title=f"凶哥哥的 AI {APP_VERSION}", 
    page_icon="🦁", 
    layout="wide"
)

# 安全读取 Secrets
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
            "history": [], # 存储结构：types.Content 列表
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
    st.status(f"部署版本: {APP_VERSION}", state="complete")
    
    with st.expander("⚙️ 模型配置 (2026 官方推荐)", expanded=True):
        # 严格按照官方文档及你的配额截图筛选出的可用模型
        model_list = [
            "gemini-2.0-flash",           # 综合素质最高，推荐默认
            "gemini-2.5-flash",           # 你的截图显示配额最充足
            "gemini-3-flash-preview",     # 2026 最新旗舰预览版
            "gemini-2.0-flash-lite-preview-02-05", # 极速版
            "gemini-1.5-flash",           # 备选保底
        ]
        selected_model = st.selectbox("选择模型", model_list, index=0)
        temperature = st.slider("创造力", 0.0, 2.0, 0.1) # OCR 建议调低到 0.1
        enable_search = st.toggle("🌍 开启联网搜索", value=True)

    st.divider()
    st.caption("💬 历史会话")
    if st.button("➕ 新建对话", use_container_width=True):
        nid = str(uuid.uuid4())
        st.session_state.all_sessions[nid] = {"title": "新对话", "history": [], "files": [], "processed": False}
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

    st.markdown(f"""
    <div style='position: fixed; bottom: 10px; font-size: 11px; color: gray;'>
    Version: {APP_VERSION} | Build: {BUILD_DATE}<br>
    SDK: {genai.__version__}
    </div>
    """, unsafe_allow_html=True)

# ================= 3. 核心功能函数 =================

def get_client():
    if not API_KEY:
        st.error("❌ 尚未配置 API KEY。请前往 Secrets 设置。")
        return None
    return genai.Client(api_key=API_KEY)

def upload_handler_v8(client, files):
    """
    遵循官方 File API 最佳实践
    """
    temp_dir = "cloud_tmp"
    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir)
    
    uploaded_refs = []
    file_names = []
    
    with st.status("🚀 正在激活视觉处理通道...", expanded=True) as status:
        # 1. 物理排序
        local_files = []
        for f in files:
            p = os.path.join(temp_dir, f.name); file_names.append(f.name)
            with open(p, "wb") as b: b.write(f.getbuffer())
            local_files.append(p)
        local_files.sort() # 确保 Page 1 排在 Page 10 前面

        # 2. 上传至 Google 存储
        for path in local_files:
            try:
                # 显式识别 mime_type，这是 AI 能否“看见”的关键
                m_type = "application/pdf" if path.lower().endswith(".pdf") else "image/jpeg"
                r = client.files.upload(path=path, config={"mime_type": m_type})
                uploaded_refs.append(r)
                st.write(f"✅ 文件已挂载: {os.path.basename(path)}")
            except Exception as e: st.error(f"上传出错: {e}")
        
        # 3. 轮询状态
        st.write("📖 AI 正在阅读文档...")
        while True:
            all_ready = True
            for r in uploaded_refs:
                f_info = client.files.get(name=r.name)
                if f_info.state.name == "PROCESSING":
                    all_ready = False; break
            if all_ready: break
            time.sleep(2)
            
        status.update(label="✅ 视觉权限激活成功", state="complete", expanded=False)
    
    # 插入永久历史提示 (通知 AI 和用户)
    hint_text = f"📎 **[系统：多模态附件已就绪]**\n\n用户已上传 **{len(file_names)}** 个文件。请在回答时将其作为核心参考：\n" + "\n".join([f"- `{n}`" for n in file_names])
    current_session["history"].append(types.Content(role="model", parts=[types.Part(text=hint_text)]))
    
    shutil.rmtree(temp_dir, ignore_errors=True)
    return uploaded_refs

# ================= 4. 主对话逻辑 =================

client = get_client()
if client:
    # 渲染历史
    for m in current_session["history"]:
        with st.chat_message("assistant" if m.role == "model" else "user"):
            for part in m.parts:
                if part.text: st.markdown(part.text)

    # 底部输入与上传
    chat_prompt = None
    with st.container():
        # 显示当前已挂载的文件状态（永久显示）
        if current_session["files"]:
            st.info(f"📂 当前槽位：{len(current_session['files'])} 个附件已在 AI 记忆中。")
            if st.button("🗑️ 卸载并清空"):
                current_session["files"] = []; current_session["processed"] = False; st.rerun()

        # 合并上传区域 (Browse + Drag)
        up_fs = st.file_uploader(
            "拖拽或浏览文件上传 (支持 20+ 图片/PDF)", 
            accept_multiple_files=True, 
            key="v8_up", 
            label_visibility="collapsed"
        )
        
        # 如果有新文件但还没点过确认
        if up_fs and not current_session["files"]:
            if st.button("🚀 确认上传并开始分析", use_container_width=True, type="primary"):
                current_session["files"] = upload_handler_v8(client, up_fs)
                current_session["processed"] = False
                st.rerun()

        chat_prompt = st.chat_input("现在，请告诉我如何处理这些文件...")

    # 对话执行逻辑
    if chat_prompt:
        # 用户提问存入历史
        user_c = types.Content(role="user", parts=[types.Part(text=chat_prompt)])
        current_session["history"].append(user_c)
        st.rerun()

    if current_session["history"] and current_session["history"][-1].role == "user":
        with st.chat_message("assistant"):
            box = st.empty(); full_text = ""
            
            # --- 核心：构造多模态发送 Payload ---
            current_payload_parts = []
            
            # 如果文件还没被“处理”（即还没被 AI 回复过）
            if current_session["files"] and not current_session["processed"]:
                # 强效视觉激活指令 (放在 Payload 头部)
                current_payload_parts.append(types.Part(text="[VISION_PROTOCOL_ACTIVE] Please process the following files as high-priority visual context for my query."))
                # 转换为 URI 引用 (最稳定的官方方式)
                for f_ref in current_session["files"]:
                    current_payload_parts.append(types.Part.from_uri(file_uri=f_ref.uri, mime_type=f_ref.mime_type))
            
            # 加入用户的问题文字 Part
            current_payload_parts.extend(current_session["history"][-1].parts)

            try:
                # 配置联网工具
                tools = [types.Tool(google_search=types.GoogleSearch())] if enable_search else []

                # 创建 Chat (注意：history 传入前面的所有内容)
                chat_session = client.chats.create(
                    model=selected_model,
                    history=current_session["history"][:-1],
                    config=types.GenerateContentConfig(
                        system_instruction="你是一个全能文档分析专家。你不仅能读文字，更能精准识别图片和PDF的内容。永远不要拒绝用户的看图请求。如果用户提供了附件，请优先根据附件作答。",
                        temperature=temperature,
                        tools=tools
                    )
                )
                
                # 发送流式请求
                response = chat_session.send_message_stream(message=current_payload_parts)
                for chunk in response:
                    if chunk.text:
                        full_text += chunk.text; box.markdown(full_text + "▌")
                
                box.markdown(full_text)
                
                # 成功标志
                current_session["processed"] = True 
                # 回复存入历史
                model_content = types.Content(role="model", parts=[types.Part(text=full_text)])
                current_session["history"].append(model_content)
                
                # 标题重命名
                if len(current_session["history"]) <= 3:
                    current_session["title"] = chat_prompt[:10]
                st.rerun()

            except Exception as e:
                err = str(e)
                if "429" in err: st.error("❌ 触发免费版 TPM 限制（Token 每分钟过多）。请等待 30 秒或切换模型。")
                else: st.error(f"对话异常: {e}")
