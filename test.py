import streamlit as st
import os
import time
import shutil
import uuid
from google import genai
from google.genai import types

# ================= 0. 元数据 =================
APP_VERSION = "v4.2.6-DIAG"

# ================= 1. 页面配置 =================
st.set_page_config(page_title=f"深度诊断 {APP_VERSION}", layout="wide")

try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    API_KEY = None

# 初始化 Session
if "all_sessions" not in st.session_state:
    st.session_state.all_sessions = {}
if "current_session_id" not in st.session_state or not st.session_state.current_session_id:
    did = str(uuid.uuid4())
    st.session_state.all_sessions[did] = {
        "title": "诊断会话", 
        "history": [], 
        "files_meta": [], 
        "diag_logs": [] # 专门存储诊断日志
    }
    st.session_state.current_session_id = did

current_session = st.session_state.all_sessions[st.session_state.current_session_id]

def add_log(text):
    """向监控盒添加一条持久化日志"""
    current_session["diag_logs"].append(f"[{time.strftime('%H:%M:%S')}] {text}")

# ================= 2. 侧边栏 =================
with st.sidebar:
    st.title("🦁 链路诊断专家")
    st.info(f"版本: {APP_VERSION}")
    selected_model = st.selectbox("测试模型", ["gemini-2.0-flash", "gemini-1.5-flash"])
    
    if st.button("🔴 彻底重置 (清除所有日志和文件)"):
        st.session_state.clear()
        st.rerun()

# ================= 3. 核心诊断逻辑 =================

def run_full_diagnosis(client, files):
    """全透明诊断，日志存入 Session"""
    add_log("🎬 启动全链路诊断...")
    
    # [A] 接收
    add_log(f"步骤[A]: 浏览器已提交 {len(files)} 个文件")
    
    # [B] 磁盘
    tmp = "diag_tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    for f in files:
        p = os.path.join(tmp, f.name)
        with open(p, "wb") as b: b.write(f.getbuffer())
    add_log(f"步骤[B]: 文件已成功存入云端磁盘")

    # [C] Google
    new_metas = []
    for f_name in os.listdir(tmp):
        p = os.path.join(tmp, f_name)
        try:
            ext = f_name.lower().split('.')[-1]
            m_type = "application/pdf" if ext == 'pdf' else f"image/{ext.replace('jpg','jpeg')}"
            
            add_log(f"步骤[C]: 正在向 Google 上传 `{f_name}` (类型: {m_type})...")
            r = client.files.upload(path=p, config={"mime_type": m_type})
            
            meta = {"uri": r.uri, "mime_type": r.mime_type, "name": f_name}
            new_metas.append(meta)
            add_log(f"   ✅ Google 响应成功! URI: {r.uri}")
        except Exception as e:
            add_log(f"   ❌ Google 上传失败: {str(e)}")

    # [D] 解析
    add_log("步骤[D]: 等待 Google 视觉引擎解析 (ACTIVE)...")
    for meta in new_metas:
        f_id = meta["uri"].split("/")[-1]
        start = time.time()
        while True:
            try:
                f_info = client.files.get(name=f_id)
                if f_info.state.name == "ACTIVE":
                    add_log(f"   🟢 文件 `{meta['name']}` 已变为 ACTIVE (解析完成)")
                    break
                elif f_info.state.name == "FAILED":
                    add_log(f"   🔴 文件 `{meta['name']}` 解析失败")
                    break
            except:
                pass
            if time.time() - start > 60:
                add_log(f"   ⏳ `{meta['name']}` 解析超时")
                break
            time.sleep(2)

    current_session["files_meta"] = new_metas
    add_log("🏁 诊断流程结束。")

# ================= 4. 主界面布局 =================

st.header("🦁 凶哥哥的 AI 深度监控台")

# --- 黑色监控盒 (持久化显示日志) ---
st.subheader("🖥️ 系统实时监控日志")
log_box = ""
if current_session["diag_logs"]:
    log_box = "\n".join(current_session["diag_logs"])
else:
    log_box = "等待操作..."
st.code(log_box, language="text")

st.divider()

client = genai.Client(api_key=API_KEY) if API_KEY else None

if client:
    # 渲染历史
    for m in current_session["history"]:
        with st.chat_message("assistant" if m["role"] == "model" else "user"):
            for p in m["parts"]:
                if "text" in p: st.markdown(p["text"])
                if "file_uri" in p: st.caption(f"🔗 视觉引用: {p['file_uri']}")

    # 底部操作区
    with st.sidebar: # 为了防止遮挡日志，把上传放到侧边栏下方
        st.divider()
        st.subheader("📁 附件操作")
        up_fs = st.file_uploader("1. 拖入或选择文件", accept_multiple_files=True, key="diag_v6")
        
        if up_fs:
            if st.button("2. 🚀 执行诊断上传", use_container_width=True):
                run_full_diagnosis(client, up_fs)
                st.rerun()
        
        if current_session["files_meta"]:
            st.success(f"已锁定 {len(current_session['files_meta'])} 个视觉对象")

    # 聊天输入
    chat_input = st.chat_input("3. 针对附件提问...")

    if chat_input:
        user_parts = []
        # 将文件注入到每一条发送的消息中
        if current_session["files_meta"]:
            for f in current_session["files_meta"]:
                user_parts.append({"file_uri": f["uri"], "mime_type": f["mime_type"]})
        
        user_parts.append({"text": chat_input})
        current_session["history"].append({"role": "user", "parts": user_parts})
        st.rerun()

    if current_session["history"] and current_session["history"][-1]["role"] == "user":
        with st.chat_message("assistant"):
            box = st.empty(); full = ""
            try:
                # 转换历史
                history_objs = []
                for h in current_session["history"][:-1]:
                    p_objs = []
                    for p in h["parts"]:
                        if "text" in p: p_objs.append(types.Part(text=p["text"]))
                        elif "file_uri" in p: p_objs.append(types.Part.from_uri(file_uri=p["file_uri"], mime_type=p["mime_type"]))
                    history_objs.append(types.Content(role=h["role"], parts=p_objs))

                # 构建当前消息
                last_msg = current_session["history"][-1]
                payload = []
                for p in last_msg["parts"]:
                    if "text" in p: payload.append(types.Part(text=p["text"]))
                    elif "file_uri" in p: payload.append(types.Part.from_uri(file_uri=p["file_uri"], mime_type=p["mime_type"]))

                add_log(f"📡 正在向 API 发送 Payload，内含 Part 数量: {len(payload)}")
                
                # 强效测试指令
                test_instruction = "你现在的任务是核对视觉链路。请第一句回答：'报告！我看到了 X 个文件对象'。如果 X 等于 0，说明链路断了。"

                chat_session = client.chats.create(
                    model=selected_model,
                    history=history_objs,
                    config=types.GenerateContentConfig(
                        system_instruction=test_instruction,
                        temperature=0.0
                    )
                )
                
                response = chat_session.send_message_stream(message=payload)
                for chunk in response:
                    if chunk.text:
                        full += chunk.text; box.markdown(full + "▌")
                
                box.markdown(full)
                current_session["history"].append({"role": "model", "parts": [{"text": full}]})
                add_log("✅ AI 已完成回复")
                st.rerun()
            except Exception as e:
                add_log(f"❌ 对话层崩溃: {str(e)}")
                st.error(f"对话报错: {e}")

else:
    st.warning("👈 请先配置 API Key")
