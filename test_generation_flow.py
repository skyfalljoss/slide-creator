import json
import urllib.request
import urllib.error
import time

BASE_URL = "http://localhost:8000/api/v1"

def make_post_request(endpoint, data):
    url = f"{BASE_URL}{endpoint}"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.reason}")
        print(e.read().decode("utf-8"))
        raise
    except Exception as e:
        print(f"Connection failed: {e}")
        print("Make sure your backend server is running on http://localhost:8000!")
        raise

def main():
    print("Step 1: Requesting slide generation (Sales Deck, 9 slides)...")
    gen_data = {
        "prompt": "Create a proposal for a Strategic AI Integration Partnership with Acme Retail Group, focusing on customer service automation and supply chain optimization.",
        "deck_type": "sales_9"
    }
    
    start_time = time.time()
    try:
        gen_resp = make_post_request("/generate", gen_data)
    except Exception:
        return
        
    print(f"Slide generation complete in {time.time() - start_time:.2f} seconds.")
    session_id = gen_resp["session_id"]
    slides = gen_resp["slides"]
    
    print(f"\nGenerated Session ID: {session_id}")
    print(f"Total Slides: {len(slides)}")
    
    image_count = 0
    for s in slides:
        has_img = s.get("image_b64") is not None
        if has_img:
            image_count += 1
        print(f"  Slide {s['index']} [{s['layout']}]: Title='{s['title']}' | Has Image? {has_img}")
        
    print(f"\nTotal slides with AI images generated: {image_count}")
    
    print("\nStep 2: Exporting slides to PPTX...")
    export_resp = make_post_request("/export", {"session_id": session_id})
    download_url = export_resp["download_url"]
    if download_url.startswith("/"):
        download_url = f"http://localhost:8000{download_url}"
    
    print(f"Export complete. Download URL: {download_url}")
    
    # Download the exported file
    filename = "test_output.pptx"
    print(f"\nStep 3: Downloading PPTX presentation to {filename}...")
    try:
        urllib.request.urlretrieve(download_url, filename)
        print(f"Success! Saved presentation as '{filename}' in the root directory.")
    except Exception as e:
        print(f"Failed to download file: {e}")

if __name__ == "__main__":
    main()
