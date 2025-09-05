import asyncio
from playwright.async_api import async_playwright
from jinja2 import Template
import os
import base64
import uuid
from pathlib import Path
import platform
import io
import asyncio, sys
import shutil  # put this at the top with your imports
# Fix Playwright subprocess issue on Windows
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

HTML_TEMPLATE = """
<html>
<head>
  <style>
    @font-face {
      font-family: 'Fallback';
      src: url('file://{{ fallback_font }}');
    }
    @font-face {
      font-family: 'Symbola';
      src: url('file://{{ symbola_font }}');
    }
    @font-face {
      font-family: 'DejaVu';
      src: url('file://{{ dejavu_font }}');
    }
    @font-face {
      font-family: 'Arial';
      src: url('file://{{ arial_font }}');
    }
    @font-face {
      font-family: 'DejaVuBold';
      src: url('file://{{ dejavu_bold }}');
    }
    @font-face {
      font-family: 'ArialUnicode';
      src: url('file://{{ arial_unicode }}');
    }

    html, body {
      margin: 0;
      padding: 0;
      background: transparent;
    }

    .wrapper {
      display: inline-flex;
      align-items: center;
      background: transparent;
      padding: 8px;
    }

    .pfp {
      width: 60px;
      height: 60px;
      border-radius: 50%;
      object-fit: cover;
      margin-right: 12px;
      flex-shrink: 0;
    }

    .container {
      font-family: 'Segoe UI','DejaVuBold','DejaVu','ArialUnicode','Symbola','Fallback','Arial','Noto Color Emoji',sans-serif;
      background: linear-gradient(90deg, #191423, #231c33);
      border-radius: 20px;
      color: white;
      padding: 16px 20px;
      display: flex;
      flex-direction: column;
      justify-content: center;
      max-width: max-content;
    }

    .name {
      font-size: 24px;
      color: cyan;
      line-height: 1.2;
    }

    .message {
      font-size: 28px;
      line-height: 1.3;
      max-width: 400px;           /* limit width to enable wrapping */
      white-space: pre-wrap;      /* preserve existing line breaks */
      word-wrap: break-word;      /* break long words */
      word-break: break-word;
      overflow-wrap: break-word;
    }

  </style>
</head>
<body>
  <div class="wrapper">
    {% if profile_image %}
      <img src="{{ profile_image }}" class="pfp" />
    {% endif %}
    <div class="container">
      <div class="name">{{ name }}</div>
      <div class="message">{{ message }}</div>
    </div>
  </div>
</body>
</html>
"""

async def create_quote_image(name, message, profile_image=None, output_path="sticker.png"):
    # Absolute font paths - UPDATE THESE TO YOUR ACTUAL PATHS
    fallback_font = "fonts/unifont-16.0.04.otf"
    symbola_font  = "fonts/Symbola.ttf"
    dejavu_font   = "fonts/DejaVuSans.ttf"
    dejavu_bold   = "fonts/DejaVuSans-Bold.ttf"
    arial_unicode = "fonts/arial unicode ms.otf"
    arial_font    = "fonts/arial.ttf"



    temp_profile_uri = None

    if profile_image and os.path.exists(profile_image):
        try:
            ext = os.path.splitext(profile_image)[-1].lower()
            mime_type = "image/jpeg"  # default
            if ext == ".png":
                mime_type = "image/png"
            elif ext == ".gif":
                mime_type = "image/gif"
            
            with open(profile_image, "rb") as img_file:
                encoded_string = base64.b64encode(img_file.read()).decode("utf-8")
                temp_profile_uri = f"data:{mime_type};base64,{encoded_string}"
        except Exception as e:
            print(f"[⚠️] Failed to process profile image: {e}")

    html = Template(HTML_TEMPLATE).render(
        name=name,
        message=message,
        profile_image=temp_profile_uri,
        fallback_font=fallback_font,
        symbola_font=symbola_font,
        dejavu_font=dejavu_font,
        arial_font=arial_font,
    )

    try:
        async with async_playwright() as p:
            import shutil  # put this at the top with your imports

            if platform.system() == "Windows":
    # Find installed Chrome/Edge explicitly
                chrome_path = shutil.which("chrome") or shutil.which("chrome.exe") \
                              or shutil.which("msedge") or shutil.which("msedge.exe")
                if not chrome_path:
                    raise RuntimeError("Chrome/Edge not found. Please install Chrome or Edge on Windows.")

                browser = await p.chromium.launch(
                    headless=True,
                    executable_path=chrome_path
                )
            else:
                # Use default bundled Chromium on Linux/Render
                browser = await p.chromium.launch(headless=True)


            page = await browser.new_page()
            await page.set_content(html)
            await page.wait_for_timeout(500)
            wrapper = await page.query_selector(".wrapper")
            if wrapper:
                await wrapper.screenshot(
                    path=output_path,
                    type="png",
                    omit_background=True,
                )
                print(f"[✅] Sticker saved to: {os.path.abspath(output_path)}")

                # ✅ Convert file to BytesIO for Telegram
                with open(output_path, "rb") as f:
                    bio = io.BytesIO(f.read())
                    bio.name = "sticker.png"
                    bio.seek(0)
                    return bio

            else:
                print("[❌] Error: Could not find .wrapper element in HTML")
            await browser.close()
    except Exception as e:
        print(f"[❌] Playwright error: {e}")
        raise

async def send_quote_sticker(bot, chat_id, name, message, profile_image=None):
    # Create a temp directory if it doesn't exist
    temp_dir = os.path.join(os.getcwd(), "temp_stickers")
    os.makedirs(temp_dir, exist_ok=True)
    
    # Generate unique filename
    output_path = os.path.join(temp_dir, f"sticker_{uuid.uuid4().hex}.png")
    
    try:
        # Generate the sticker
        await create_quote_image(name, message, profile_image, output_path)
        
        # Verify the file was created
        if not os.path.exists(output_path):
            await bot.send_message(chat_id, "⚠️ Failed to generate sticker. Please try again!")
            return
        
        # Send the sticker
        with open(output_path, "rb") as sticker_file:
            await bot.send_photo(chat_id, sticker_file)
            
    except Exception as e:
        await bot.send_message(chat_id, "❌ An error occurred while creating the sticker")
        print(f"Error in send_quote_sticker: {e}")
        
    finally:
        # Clean up: delete the temp file
        try:
            if os.path.exists(output_path):
                os.remove(output_path)
        except Exception as e:
            print(f"Error deleting temp file: {e}")

# Example usage in a Telegram bot handler:
"""
@bot.message_handler(content_types=['text', 'photo'])
async def handle_message(message):
    try:
        # Get profile picture if available
        profile_pic = None
        if message.from_user.photo:
            file_info = await bot.get_file(message.from_user.photo[-1].file_id)
            profile_pic = await bot.download_file(file_info.file_path)
            
        await send_quote_sticker(
            bot,
            message.chat.id,
            message.from_user.first_name,
            message.text,
            profile_pic
        )
    except Exception as e:
        print(f"Handler error: {e}")

"""





