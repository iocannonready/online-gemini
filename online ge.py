import streamlit as st
from google import genai
import os
import tempfile
from typing import Optional

# 配置页面
st.set_page_config(
    page_title="Online Gemini Chat",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 初始化 session_state
if "api_key" not in st.session_state:
    st.session_state.api_key = None
if "client" not in st.session_state:
    st.session_state.client = None
if "file_content" not in st.session_state:
    st.session_state.file_content = None
if "file_name" not in st.session_state:
    st.session_state.file_name = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "model_selected" not in st.session_state:
    st.session_state.model_selected = "gemini-2.5-flash"

# 可用模型列表
AVAILABLE_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-3-flash-preview",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]

# 侧边栏设置
st.sidebar.title("⚙️ 配置")

# API Key 输入
api_key_input = st.sidebar.text_input(
    "输入 Google Gemini API Key:",
    type="password",
    placeholder="sk-..."
)

if api_key_input and api_key_input != st.session_state.api_key:
    try:
        # 配置新的客户端
        st.session_state.api_key = api_key_input
        st.session_state. client = genai.Client(api_key=api_key_input)
        st.sidebar.success("✅ API Key 已验证")
    except Exception as e:
        st.sidebar.error(f"❌ API Key 配置失败: {str(e)}")
        st.session_state.api_key = None
        st.session_state. client = None

# 模型选择
st.sidebar.title("🤖 模型选择")
model_selected = st.sidebar.selectbox(
    "选择 Gemini 模型:",
    AVAILABLE_MODELS,
    index=AVAILABLE_MODELS.index(st.session_state.model_selected),
    key="model_selector"
)
st.session_state.model_selected = model_selected

if st.session_state.client: 
    st.sidebar.info(f"📌 当前模型: **{model_selected}**")

# 文件上传区域
st.sidebar.title("📁 文件上传")
uploaded_file = st.sidebar.file_uploader(
    "选择文件（支持 txt, pdf, md, json, csv）:",
    type=["txt", "pdf", "md", "json", "csv"],
    key="file_uploader"
)

# 处理上传的文件
def process_uploaded_file(file) -> Optional[str]:
    """处理上传的文件并返回其内容"""
    if file is None:
        return None
    
    try:
        file_name = file.name
        
        # 文本文件处理
        if file. type == "text/plain" or file_name.endswith((".txt", ".md", ".json", ".csv")):
            content = file.read().decode("utf-8")
            st.sidebar.success(f"✅ 已读取: {file_name}")
            st.sidebar.caption(f"📊 文件大小: {len(content):,} 字符")
            return content
        
        # PDF 处理
        elif file. type == "application/pdf" or file_name.endswith(".pdf"):
            with tempfile. NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(file.getbuffer())
                tmp_path = tmp.name
            st.sidebar.success(f"✅ 已加载 PDF: {file_name}")
            st.sidebar.warning("⚠️ PDF 内容识别需要手动提取")
            return f"[PDF文件:  {file_name}]"
        
    except UnicodeDecodeError:
        st.sidebar.error("❌ 文件编码错误，请确保文件是 UTF-8 格式")
    except Exception as e:
        st.sidebar.error(f"❌ 文件处理失败: {str(e)}")
    
    return None

# 处理上传的文件
if uploaded_file is not None:
    file_content = process_uploaded_file(uploaded_file)
    if file_content:
        st. session_state.file_content = file_content
        st.session_state.file_name = uploaded_file.name

# 主界面
st.title("🤖 Online Gemini Chat")

if not st.session_state.client:
    st.warning("🔑 **请在左侧边栏输入 Google Gemini API Key 来开始使用**")
    st.info("""
    ### 如何获取 API Key? 
    1. 访问 [Google AI Studio](https://ai.google.dev)
    2. 点击 "Get API Key"
    3. 创建新的 API Key
    4. 复制并粘贴到上方输入框
    """)
else:
    # 显示已上传文件信息
    if st.session_state.file_name and st.session_state.file_content:
        with st.expander(f"📄 已上传文件:  **{st.session_state.file_name}**"):
            preview_text = st.session_state.file_content
            if len(preview_text) > 1000:
                preview_text = preview_text[:1000] + "\n\n... (内容已截断)"
            st.text_area(
                "文件内容预览:",
                value=preview_text,
                height=200,
                disabled=True
            )
    
    # 聊天历史显示
    st.subheader("💬 对话历史")
    
    chat_container = st.container()
    with chat_container:
        for message in st.session_state.chat_history:
            if message["role"] == "user":
                with st.chat_message("user", avatar="👤"):
                    st.markdown(message["content"])
            else:
                with st.chat_message("assistant", avatar="🤖"):
                    st. markdown(message["content"])
    
    # 输入区域
    st.divider()
    
    col1, col2 = st. columns([0.88, 0.12])
    
    with col1:
        user_input = st.text_input(
            "输入你的问题:",
            placeholder="输入问题或与上传文件相关的问题.. .",
            key="user_input"
        )
    
    with col2:
        send_button = st.button("📤 发送", use_container_width=True, type="primary")
    
    # 处理用户输入
    if send_button and user_input: 
        try:
            # 构建完整 prompt
            full_prompt = user_input
            
            if st.session_state.file_content:
                # 如果有上传的文件，将其内容包含在消息中
                full_prompt = f"""请基于以下文件内容回答问题: 

【文件名】{st.session_state.file_name}

【文件内容】
{st.session_state.file_content}

【用户问题】
{user_input}"""
            
            # 添加用户消息到历史
            st.session_state.chat_history.append({
                "role": "user",
                "content": user_input
            })
            
            # 显示用户消息
            with st.chat_message("user", avatar="👤"):
                st.markdown(user_input)
            
            # 调用 Gemini API (新 SDK)
            with st.spinner("🔄 Gemini 正在思考..."):
                response = st.session_state.client.models.generate_content(
                    model=st.session_state.model_selected,
                    contents=full_prompt,
                    config={
                        "temperature": 0.7,
                        "max_output_tokens": 2048,
                    }
                )
                
                assistant_message = response.text
            
            # 添加助手回复到历史
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": assistant_message
            })
            
            # 显示助手回复
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(assistant_message)
            
            # 重新运行以更新 UI
            st.rerun()
        
        except Exception as e: 
            st.error(f"❌ 发生错误: {str(e)}")
            st.info("💡 提示: 确保 API Key 有效且未超过配额限制")
    
    # 底部控制按钮
    st.divider()
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🗑️ 清空对话", use_container_width=True):
            st.session_state.chat_history = []
            st.rerun()
    
    with col2:
        if st.button("📋 清除文件", use_container_width=True):
            st.session_state. file_content = None
            st.session_state.file_name = None
            st.rerun()
    
    with col3:
        if st.button("🔄 重新初始化", use_container_width=True):
            st.session_state.clear()
            st.rerun()
    
    # 使用统计信息
    st.sidebar.divider()
    st.sidebar.title("📊 统计信息")
    st.sidebar.metric("对话轮数", len(st.session_state.chat_history) // 2)
    st.sidebar.metric("已上传文件", "有" if st.session_state.file_name else "无")
