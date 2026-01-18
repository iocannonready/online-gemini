import streamlit as st
import os
import time
import shutil
import uuid
# 【核心】使用 Google 官方新版 SDK 命名空间
from google import genai
from google.genai import types

# ================= 0. 配置与版本 =================
APP_VERSION = "v5.2.0-CLOUD-OFFICIAL"
st.set_page_config(page_title=f"凶哥哥 AI {APP_VERSION}", page_icon="🦁", layout="wide")

# 从 Streamlit Secrets 获取 API Key
try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except KeyError:
    st.error("❌ 未检测到 API Key。请在 Streamlit App Settings -> Secrets 中配置 GOOGLE_API_KEY。")
    st.stop()

# ================= 1. Session State 初始化 =================
if "all_sessions" not in st.session_state:
    default_id = str(uuid.uuid4())
    st.session_state.all_sessions = {
        default_id: {
            "title": "新对话",
            # history 存储纯字典数据，避免 SDK 对象序列化报错
            # 格式: {"role": "user"/"model", "parts": [{"text": "..."}, {"file_uri": "...", "mime_type": "..."}]}
            "history": [], 
            "files_meta": [], 
            "processed": False
        }
    }
    st.session_state.current_session_id = default_id

def get_current_session():
    sid = st.session_state.current_session_id
    # 防止删除当前会话后报错，回退到第一个
    if sid not in st.session_state.all_sessions:
        if not st.session_state.all_sessions:
             new_id = str(uuid.uuid4())
             st.session_state.all_sessions[new_id] = {"title": "新对话", "history": [], "files_meta": [], "processed": False}
        sid = list(st.session_state.all_sessions.keys())[0]
        st.session_state.current_session_id = sid
    return st.session_state.all_sessions[sid]

current_session = get_current_session()

# ================= 2. 核心功能函数 (官方标准写法) =================

def get_client():
    # 云端直连，无需代理配置
    return genai.Client(api_key=API_KEY)

def upload_file_standard(client, uploaded_file):
    """
    遵循官方文档 'Files' 章节的上传逻辑
    """
    temp_dir = "temp_cloud_upload"
    if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    
    file_meta = None
    
    try:
        # 1. 保存到临时路径 (解决中文文件名编码问题)
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        if not ext: ext = ".pdf" if uploaded_file.type == "application/pdf" else ".jpg"
        
        # 使用时间戳重命名，彻底规避 SDK 的 ASCII 编码 Bug
        safe_filename = f"upload_{int(time.time())}{ext}"
        local_path = os.path.join(temp_dir, safe_filename)
        
        with open(local_path, "wb") as b:
            b.write(uploaded_file.getbuffer())
            
        # 2. 识别 MIME 类型
        mime_type = "application/pdf" if ext == ".pdf" else "image/jpeg"
        if "png" in ext: mime_type = "image/png"
        
        # 3. 上传 (官方参数名为 file)
        # 文档: client.files.upload(file=...)
        uploaded_file_obj = client.files.upload(file=local_path, config={"mime_type": mime_type})
        
        # 4. 等待处理完成 (Active)
        while True:
            # 文档: client.files.get(name=...)
            f_info = client.files.get(name=uploaded_file_obj.name)
            if f_info.state.name == "ACTIVE":
                break
            elif f_info.state.name == "FAILED":
                raise Exception("Google 服务器处理文件失败")
            time.sleep(1)
            
        # 返回元数据
        file_meta = {
            "uri": uploaded_file_obj.uri,
            "mime_type": uploaded_file_obj.mime_type,
            "name": uploaded_file_obj.name,
            "display_name": uploaded_file.name
        }
        
    except Exception as e:
        st.error(f"上传失败: {e}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        
    return file_meta

# ================= 3. 侧边栏 UI =================
with st.sidebar:
    st.header("🦁 凶哥哥的 AI")
    st.caption(f"Cloud Native | {APP_VERSION}")
    
    with st.expander("⚙️ 模型配置", expanded=True):
        # 筛选出的 2026 可用模型
        model_list = [
            "gemini-2.5-flash",       # 主力推荐
            "gemini-2.5-flash-lite",  # 极速省流
            "gemini-2.0-flash",       # 经典稳定
        ]
        selected_model = st.selectbox("选择模型", model_list, index=0)
        temperature = st.slider("创造力", 0.0, 1.0, 0.2)
        enable_search = st.toggle("联网搜索", value=True)

    st.divider()
    
    # --- 附件管理 (集成在侧边栏) ---
    st.subheader("📁 附件管理")
    uploaded_files = st.file_uploader(
        "添加图片/PDF", 
        type=['pdf', 'png', 'jpg', 'jpeg'], 
        accept_multiple_files=True,
        label_visibility="collapsed"
    )
    
    # 自动触发上传逻辑
    if uploaded_files:
        client = get_client()
        # 检查新文件
        existing_names = [f['display_name'] for f in current_session["files_meta"]]
        new_files = [f for f in uploaded_files if f.name not in existing_names]
        
        if new_files:
            with st.status("📡 正在同步至 Google...", expanded=True):
                for f in new_files:
                    meta = upload_file_standard(client, f)
                    if meta:
                        current_session["files_meta"].append(meta)
                        st.write(f"✅ {f.name} 就绪")
                current_session["processed"] = False # 有新文件，重置处理状态
                st.rerun()

    # 显示已挂载文件
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

# 1. 渲染历史消息
for msg in current_session["history"]:
    with st.chat_message("assistant" if msg["role"] == "model" else "user"):
        # 渲染纯文本部分
        for part in msg["parts"]:
            if "text" in part:
                st.markdown(part["text"])
            # 如果历史里有文件引用，也可以渲染个小图标提示
            if "file_uri" in part:
                st.caption(f"📄 [附件已发送]")

# 2. 底部输入框 (始终置底)
prompt = st.chat_input("输入问题...")

# 3. 处理发送逻辑
if prompt:
    # --- A. 构造用户消息 (User Content) ---
    user_parts_storage = [] # 用于存入 Session 的格式 (纯字典)
    user_parts_api = []     # 用于发给 API 的格式 (types.Part)
    
    # 如果有附件且未处理，或者是第一轮，强制带上附件
    # 官方推荐：Use types.Part.from_uri
    if current_session["files_meta"] and not current_session["processed"]:
        # 插入系统提示 (可选，增强效果)
        sys_hint = "请基于以下附件内容回答："
        user_parts_storage.append({"text": sys_hint})
        user_parts_api.append(types.Part.from_text(text=sys_hint))
        
        for f in current_session["files_meta"]:
            # 存入 Session (只存元数据)
            user_parts_storage.append({"file_uri": f["uri"], "mime_type": f["mime_type"]})
            # 发给 API (构造 Part 对象)
            user_parts_api.append(types.Part.from_uri(file_uri=f["uri"], mime_type=f["mime_type"]))
        
        current_session["processed"] = True

    # 加入用户文本
    user_parts_storage.append({"text": prompt})
    user_parts_api.append(types.Part.from_text(text=prompt))
    
    # 更新本地历史
    current_session["history"].append({"role": "user", "parts": user_parts_storage})
    
    # --- B. 构造历史上下文 (History) ---
    # 需要把 session 中的字典历史转换为 types.Content 对象列表
    api_history_objs = []
    for h in current_session["history"][:-1]: # 不包含最新这条，因为最新这条在 message 参数里
        parts_list = []
        for p in h["parts"]:
            if "text" in p:
                parts_list.append(types.Part.from_text(text=p["text"]))
            elif "file_uri" in p:
                parts_list.append(types.Part.from_uri(file_uri=p["file_uri"], mime_type=p["mime_type"]))
        
        api_history_objs.append(types.Content(role=h["role"], parts=parts_list))

    # --- C. 调用 API 生成 ---
    with st.chat_message("assistant"):
        box = st.empty()
        full_response = ""
        
        try:
            # 配置工具 (联网)
            # 文档: tools=[types.Tool(google_search=types.GoogleSearch())]
            tools_cfg = [types.Tool(google_search=types.GoogleSearch())] if enable_search else None
            
            # 创建 Chat 会话
            chat = client.chats.create(
                model=selected_model,
                history=api_history_objs,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    tools=tools_cfg,
                    system_instruction="你是一个专业的全能助手。如果用户提供了文件，请优先基于文件内容进行分析和回答。"
                )
            )
            
            # 流式发送
            response_stream = chat.send_message_stream(message=user_parts_api)
            
            for chunk in response_stream:
                if chunk.text:
                    full_response += chunk.text
                    box.markdown(full_response + "▌")
            
            box.markdown(full_response)
            
            # 存入历史
            current_session["history"].append({"role": "model", "parts": [{"text": full_response}]})
            
            # 自动重命名标题 (仅第一轮)
            if len(current_session["history"]) == 2:
                current_session["title"] = prompt[:10]
            
            st.rerun()
            
        except Exception as e:
            st.error(f"对话出错: {e}")
