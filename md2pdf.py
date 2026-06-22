import os
import markdown
from playwright.sync_api import sync_playwright

def generate_pdf():
    # Read markdown
    with open("Manual_do_Usuario.md", "r", encoding="utf-8") as f:
        md_text = f.read()
        
    # Convert to HTML
    html_body = markdown.markdown(md_text)
    
    # Wrap in full HTML with CSS styling
    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                color: #333;
                line-height: 1.6;
                padding: 40px;
                max-width: 800px;
                margin: 0 auto;
            }}
            h1 {{
                color: #2c3e50;
                border-bottom: 2px solid #3498db;
                padding-bottom: 10px;
                margin-bottom: 20px;
            }}
            h2 {{
                color: #2980b9;
                margin-top: 30px;
            }}
            ul, ol {{
                margin-bottom: 20px;
            }}
            li {{
                margin-bottom: 8px;
            }}
            strong {{
                color: #e74c3c;
            }}
            hr {{
                border: 0;
                border-top: 1px solid #ecf0f1;
                margin: 30px 0;
            }}
            code {{
                background-color: #f8f9fa;
                padding: 2px 4px;
                border-radius: 4px;
                font-family: Consolas, monospace;
            }}
        </style>
    </head>
    <body>
        {html_body}
    </body>
    </html>
    """
    
    html_path = os.path.abspath("temp_manual.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(full_html)
        
    # Use Playwright to print PDF
    print("Iniciando Playwright para gerar o PDF...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"file:///{html_path.replace(chr(92), '/')}")
        page.pdf(path="Manual_do_Usuario.pdf", format="A4", print_background=True, margin={"top": "2cm", "bottom": "2cm", "left": "2cm", "right": "2cm"})
        browser.close()
        
    # Cleanup temporary HTML
    if os.path.exists(html_path):
        os.remove(html_path)
        
    print("PDF Gerado com Sucesso: Manual_do_Usuario.pdf")

if __name__ == "__main__":
    generate_pdf()
