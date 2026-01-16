import streamlit as st
import os
import time
import shutil
import google.generativeai as genai
from google.api_core import exceptions

# ================= 0. 默认配置区 (你可以修改这里) =================

# 你的 API Key (如果填了，打开软件就会自动带上)
DEFAULT_API_KEY = "AIzaSyBO5CPR1_0ie8tPMd-e1fBQjf4rty5x8t4" 

# 你的本地代理端口 (Clash=7890, v2rayN=10809, 其他=1080)
DEFAULT_PROXY_PORT = "1080"

# 默认是否开启代理 (你自己用设为 True，发给没梯子的朋友设为 False)
DEFAULT_USE_PROXY = True

# ================= 1. 页面初始化 =================
st.set_page_config(
    page_title="Gemini 2.5 全能助手",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 初始化 Session State (记忆功能)
if "chat_history" not in st.session_state: st.session_state.chat_history = []
if "uploaded_file_refs" not in st.session_state: st.session_state.uploaded_file_refs = []
if "chat_session" not in st.session_state: st.session_state.chat_session = None
if "files_processed" not in st.session_state: st.session_state.files_processed = False

# ================= 2. 侧边栏设置 =================
with st.sidebar:
    st.title("⚙️ 设置面板")
    
    # --- API Key ---
    api_key = st.text_input("Google API Key", value=DEFAULT_API_KEY, type="password", help="在此填入 AIza 开头的密钥")
    
    # --- 网络设置 (关键修改：增加开关) ---
    st.markdown("### 🌐 网络连接")
    use_proxy = st.checkbox("开启本地代理", value=DEFAULT_USE_PROXY, help="如果你在云端部署，或者朋友不需要梯子，请取消勾选")
    
    proxy_port = DEFAULT_PROXY_PORT
    if use_proxy:
        proxy_port = st.text_input("代理端口 (HTTP)", value=DEFAULT_PROXY_PORT)
    
    # --- 模型选择 ---
    st.markdown("### 🧠 模型选择")
    # 2026年推荐列表：Flash 系列免费且快
    model_options = [
        "gemini-2.5-flash",       # 首选：最新一代
        "gemini-2.0-flash",       # 备选：极度稳定
        "gemini-1.5-flash",       # 保底
        "gemini-1.5-pro",         # 慢，仅用于处理极度复杂的逻辑
    ]
    selected_model = st.selectbox("当前模型", model_options, index=0)
    
    st.divider()
    
    # --- 重置按钮 ---
    if st.button("🗑️ 清空对话 & 重置", type="primary"):
        st.session_state.chat_history = []
        st.session_state.uploaded_file_refs = []
        st.session_state.chat_session = None
        st.session_state.files_processed = False
        st.rerun()

# ================= 3. 功能函数 =================

def configure_env(key, enable_proxy, port):
    """配置环境和网络"""
    if not key: return False
    
    if enable_proxy:
        # 开启代理
        os.environ['HTTP_PROXY'] = f'http://127.0.0.1:{port}'
        os.environ['HTTPS_PROXY'] = f'http://127.0.0.1:{port}'
    else:
        # 关闭代理 (清除环境变量，防止残留)
        os.environ.pop('HTTP_PROXY', None)
        os.environ.pop('HTTPS_PROXY', None)
        
    genai.configure(api_key=key)
    return True

def upload_with_retry(path, max_retries=5):
    """带重试机制的文件上传"""
    file_name = os.path.basename(path)
    delay = 2
    
    for attempt in range(max_retries):
        try:
            remote_file = genai.upload_file(path)
            return remote_file
        except Exception as e:
            # 静默重试，只在最后一次报错
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay *= 2 # 指数退避
            else:
                st.error(f"❌ {file_name} 上传失败: {e}")
                return None

def process_and_upload_files(uploaded_files):
    """处理上传全流程"""
    # 1. 保存到本地缓存
    temp_dir = "temp_images_cache"
    if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    
    local_paths = []
    for f in uploaded_files:
        path = os.path.join(temp_dir, f.name)
        with open(path, "wb") as buffer:
            buffer.write(f.getbuffer())
        local_paths.append(path)
    
    local_paths.sort() # 按文件名排序
    
    # 2. 上传到 Google
    uploaded_refs = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total = len(local_paths)
    for i, path in enumerate(local_paths):
        name = os.path.basename(path)
        status_text.markdown(f"🚀 正在上传 **({i+1}/{total})**: `{name}` ...")
        
        ref = upload_with_retry(path)
        if ref: uploaded_refs.append(ref)
        
        progress_bar.progress((i + 1) / total)
    
    # 3. 等待解析 (Active 检查)
    if uploaded_refs:
        status_text.markdown("⏳ **AI 正在阅读图片内容 (Deep Reading)...**")
        with st.spinner("请稍候，Google 正在分析文档结构..."):
            wait_start = time.time()
            while True:
                all_ready = True
                for ref in uploaded_refs:
                    try:
                        # 获取最新状态
                        current = genai.get_file(ref.name)
                        if current.state.name != "ACTIVE":
                            all_ready = False
                            if current.state.name == "FAILED":
                                st.error(f"❌ 图片 {current.display_name} 解析失败")
                            break
                    except:
                        pass # 忽略网络波动
                
                if all_ready: break
                
                if time.time() - wait_start > 300: # 5分钟超时
                    st.warning("⚠️ 等待超时，尝试强制继续...")
                    break
                time.sleep(2)
                
    status_text.empty()
    progress_bar.empty()
    
    # 清理本地缓存
    try:
        shutil.rmtree(temp_dir)
    except:
        pass
        
    return uploaded_refs

# ================= 4. 主界面逻辑 =================

st.title("🤖 Gemini 2.5 文档分析助手")
st.markdown("只需拖入图片，即可一键提取文字、摘要或进行问答。")

# --- 1. 环境检查 ---
if not configure_env(api_key, use_proxy, proxy_port):
    st.warning("👈 请先在左侧侧边栏填入 API Key 才能开始使用")
    st.stop()

# --- 2. 文件上传区域 ---
with st.container():
    uploaded_files = st.file_uploader(
        "📄 上传图片 (支持批量选择)", 
        type=['png', 'jpg', 'jpeg', 'webp'], 
        accept_multiple_files=True
    )

    if uploaded_files:
        # 如果还没处理过，显示开始按钮
        if not st.session_state.uploaded_file_refs:
            col1, col2 = st.columns([1, 4])
            with col1:
                if st.button("🚀 开始分析", type="primary", use_container_width=True):
                    refs = process_and_upload_files(uploaded_files)
                    if refs:
                        st.session_state.uploaded_file_refs = refs
                        st.success(f"✅ 已成功加载 {len(refs)} 张图片到上下文！")
                        st.session_state.files_processed = False # 重置发送标记
        else:
            st.info(f"📚 当前会话已包含 {len(st.session_state.uploaded_file_refs)} 张图片 (如需更换请点击左侧重置)")

# --- 3. 聊天区域 ---
st.divider()

# 初始化模型连接
if st.session_state.chat_session is None:
    try:
        model = genai.GenerativeModel(selected_model)
        st.session_state.chat_session = model.start_chat(history=[])
    except Exception as e:
        st.error(f"连接模型失败: {e}")

# 显示历史消息
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 输入框
if prompt := st.chat_input("在此输入问题... (例如：帮我整理这些图片的内容)"):
    # 1. 显示用户输入
    st.chat_message("user").markdown(prompt)
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    
    # 2. 生成回复
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        
        try:
            # 逻辑：如果是第一句话且有图片，就把图片打包一起发
            if st.session_state.uploaded_file_refs and not st.session_state.files_processed:
                parts = [prompt] + st.session_state.uploaded_file_refs
                response = st.session_state.chat_session.send_message(parts, stream=True)
                st.session_state.files_processed = True # 标记已发过图片
            else:
                # 后续对话只发文字
                response = st.session_state.chat_session.send_message(prompt, stream=True)
            
            # 流式打印
            for chunk in response:
                full_response += chunk.text
                message_placeholder.markdown(full_response + "▌")
            message_placeholder.markdown(full_response)
            
            # 存入历史
            st.session_state.chat_history.append({"role": "assistant", "content": full_response})
            
        except Exception as e:
            st.error(f"❌ 请求出错: {e}")
            if "429" in str(e):
                st.warning("⚠️ 触发了免费版的速度限制，请喝口水，稍后再试。")