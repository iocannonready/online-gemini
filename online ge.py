import streamlit as st
import os
import time
import shutil
import uuid
import json
from google import genai
from google.genai import types

# ================= 0. 版本与配置 =================
APP_VERSION = "v5.8.0-CLOUD-FIXED-v2"
st.set_page_config(page_title=f"凶哥哥 AI {APP_VERSION}", page_icon="🦁", layout="wide")

# 【关键】安全读取 Streamlit Secrets 中的 API Key
try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except KeyError:
    st.error("❌ 未检测到 API Key。请在 Streamlit Secrets 中配置 'GOOGLE_API_KEY'")
    st.stop()

# ================= 1. 数据结构初始化 =================
if "all_sessions" not in st.session_state:
    default_id = str(uuid.uuid4())
    st.session_state. all_sessions = {
        default_id: {
            "title": "新对话", 
            "history": [], 
            "files_meta": [],
            "processed":  False
        }
    }
    st.session_state.current_session_id = default_id

def get_current_session():
    sid = st.session_state.current_session_id
    if sid not in st.session_state. all_sessions:
        if not st.session_state.all_sessions:
            new_id = str(uuid.uuid4())
            st.session_state. all_sessions[new_id] = {
                "title": "新对话", 
                "history": [], 
                "files_meta": [], 
                "processed": False
            }
            sid = new_id
        else:  
            sid = list(st.session_state.all_sessions.keys())[0]
        st.session_state.current_session_id = sid
    return st.session_state.all_sessions[sid]

current_session = get_current_session()

# ================= 2. 核心功能函数 =================

def get_client():
    """获取 Gemini API 客户端 - 云端版本"""
    # 清除任何代理设置，云端环境不需要
    os.environ.pop('HTTP_PROXY', None)
    os.environ.pop('HTTPS_PROXY', None)
    
    try:
        client = genai.Client(api_key=API_KEY)
        return client
    except Exception as e: 
        st.error(f"❌ 无法初始化 Gemini 客户端:  {e}")
        return None

def upload_file_to_gemini(client, uploaded_file):
    """
    上传文件到 Google Gemini Files API
    【关键修正】确保返回正确的文件元数据
    """
    temp_dir = ". streamlit_uploads"
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        # 保存上传的文件到临时目录
        file_path = os.path.join(temp_dir, uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        # 【关键】判断 MIME 类型
        file_ext = os.path.splitext(uploaded_file.name)[1].lower()
        mime_type_map = {
            ". pdf": "application/pdf",
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".json": "application/json",
            ".csv": "text/csv",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp"
        }
        mime_type = mime_type_map.get(file_ext, "application/octet-stream")
        
        # 【关键】调用 Gemini Files API 上传
        with st.spinner(f"📤 正在上传 {uploaded_file.name} 到 Gemini..."):
            response = client.files. upload(
                file=open(file_path, "rb"),
                config={"mime_type": mime_type}
            )
        
        file_meta = {
            "uri": response.uri,
            "mime_type": response.mime_type,
            "name": response.name,
            "display_name": uploaded_file.name,
            "size": os.path.getsize(file_path)
        }
        
        st.success(f"✅ 文件已上传:  {uploaded_file.name}")
        return file_meta
        
    except Exception as e:
        st. error(f"❌ 文件上传失败: {e}")
        return None
    finally:
        # 清理临时文件
        try:
            os.remove(file_path)
        except:
            pass

def chat_with_file(client, user_message, files_meta, chat_history, model_name):
    """
    【关键修正】与包含文件的对话
    使用正确的 API 格式：types.Part.from_text(text=.. .) 使用关键字参数
    """
    try:
        # 构建消息内容
        contents = []
        
        # 【关键】先添加文件内容
        for file_meta in files_meta: 
            contents.append(
                types.Part(
                    file_data=types.FileData(
                        mime_type=file_meta["mime_type"],
                        file_uri=file_meta["uri"]  # 使用返回的 uri
                    )
                )
            )
        
        # 【关键修正】然后添加文本消息 - 使用 text= 关键字参数
        contents.append(types.Part. from_text(text=user_message))
        
        # 【关键】构建完整的对话历史
        conversation_parts = []
        for msg in chat_history:
            if msg["role"] == "user": 
                # 【关键修正】使用 text= 关键字参数
                conversation_parts.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=msg["content"])]
                    )
                )
            else:
                # 【关键修正】使用 text= 关键字参数
                conversation_parts.append(
                    types.Content(
                        role="model",
                        parts=[types. Part.from_text(text=msg["content"])]
                    )
                )
        
        # 添加当前用户消息
        conversation_parts.append(types.Content(role="user", parts=contents))
        
        # 【关键】调用 API
        response = client.models.generate_content(
            model=model_name,
            contents=conversation_parts,
            config={
                "temperature": 0.7,
                "max_output_tokens": 4096,
            }
        )
        
        return response. text
        
    except Exception as e:
        st.error(f"❌ API 调用失败: {e}")
        import traceback
        st.error(f"详细错误:\n{traceback.format_exc()}")
        return None

def chat_without_file(client, user_message, chat_history, model_name):
    """【关键修正】无文件的纯文本对话"""
    try:
        # 构建对话历史
        conversation_parts = []
        for msg in chat_history:
            if msg["role"] == "user":
                # 【关键修正】使用 text= 关键字参数
                conversation_parts. append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=msg["content"])]
                    )
                )
            else:
                # 【关键修正】使用 text= 关键字参数
                conversation_parts.append(
                    types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=msg["content"])]
                    )
                )
        
        # 添加当前用户消息
        # 【关键修正】使用 text= 关键字参数
        conversation_parts. append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_message)]
            )
        )
        
        # 调用 API
        response = client.models.generate_content(
            model=model_name,
            contents=conversation_parts,
            config={
                "temperature": 0.7,
                "max_output_tokens":  4096,
            }
        )
        
        return response.text
        
    except Exception as e:
        st.error(f"❌ API 调用失败: {e}")
        import traceback
        st.error(f"详细错误:\n{traceback.format_exc()}")
        return None

# ================= 3. UI 布局 =================

col1, col2 = st.columns([3, 1])
with col1:
    st. title("🦁 凶哥哥 AI 助手")
with col2:
    st.caption(f"版本:  {APP_VERSION}")

# 侧边栏
with st.sidebar:
    st. title("⚙️ 设置")
    
    # 文件上传
    st.subheader("📁 上传文件")
    uploaded_files = st.file_uploader(
        "选择文件进行分析 (支持 PDF, TXT, MD, JSON, CSV, 图片等):",
        accept_multiple_files=True,
        type=["pdf", "txt", "md", "json", "csv", "jpg", "jpeg", "png", "gif", "webp"]
    )
    
    # 处理文件上传
    if uploaded_files:
        client = get_client()
        if client:
            st.info(f"🔄 检测到 {len(uploaded_files)} 个文件")
            
            # 【关键】清除旧文件元数据，重新上传
            current_session["files_meta"] = []
            
            for uploaded_file in uploaded_files: 
                file_meta = upload_file_to_gemini(client, uploaded_file)
                if file_meta:
                    current_session["files_meta"].append(file_meta)
                    st.write(f"✅ {uploaded_file.name} (大小: {file_meta['size']} 字节)")
    
    # 显示已上传文件列表
    if current_session["files_meta"]:
        st.subheader("📋 已上传文件")
        for file_meta in current_session["files_meta"]: 
            st.caption(f"✓ {file_meta['display_name']}")
    
    # 模型选择
    st.subheader("🤖 模型选择")
    model = st.selectbox(
        "选择模型:",
        ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash", "gemini-1.5-pro"],
        index=0
    )
    
    # 控制按钮
    st.divider()
    if st.button("🗑️ 清除所有文件", use_container_width=True):
        current_session["files_meta"] = []
        st.rerun()
    
    if st.button("🔄 清除对话历史", use_container_width=True):
        current_session["history"] = []
        st.rerun()

# 主聊天区域
st.subheader("💬 对话")

# 显示对话历史
chat_container = st.container()
with chat_container:
    for message in current_session["history"]: 
        if message["role"] == "user": 
            with st.chat_message("user"):
                st.markdown(message["content"])
        else:
            with st.chat_message("assistant"):
                st.markdown(message["content"])

# 输入框
user_input = st.chat_input("输入你的问题...")

# 处理用户输入
if user_input:
    client = get_client()
    
    if client is None:
        st.error("❌ 无法连接到 Gemini API，请检查 API Key 配置")
    else:
        # 添加用户消息到历史
        current_session["history"].append({
            "role": "user",
            "content": user_input
        })
        
        # 显示用户消息
        with st. chat_message("user"):
            st.markdown(user_input)
        
        # 调用 API
        with st.chat_message("assistant"):
            with st.spinner("🤖 Gemini 正在思考..."):
                if current_session["files_meta"]: 
                    # 【关键】有文件时的对话
                    response = chat_with_file(
                        client,
                        user_input,
                        current_session["files_meta"],
                        current_session["history"][:-1],  # 不包括当前用户消息
                        model
                    )
                else: 
                    # 无文件时的纯文本对话
                    response = chat_without_file(
                        client,
                        user_input,
                        current_session["history"][:-1],
                        model
                    )
                
                if response:
                    # 添加助手回复到历史
                    current_session["history"].append({
                        "role": "assistant",
                        "content": response
                    })
                    
                    st.markdown(response)
                else: 
                    st.error("❌ 未能获取响应，请检查错误信息")

# 页脚
st.divider()
st.caption(f"🔐 使用 Streamlit Secrets 安全管理 API Key | {APP_VERSION}")
