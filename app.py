import sys
sys.stdout.reconfigure(encoding='utf-8')  # ✅ Fix UnicodeEncodeError on Windows
from flask import send_from_directory
from flask import Flask, render_template, request, jsonify
import fitz  # PyMuPDF
import ollama
import os
import json
import time

app = Flask(__name__)

# Define folders
UPLOAD_FOLDER = 'uploads'
DATA_FOLDER = 'data'
DATASET_FOLDER = 'dataset'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DATA_FOLDER, exist_ok=True)
os.makedirs(DATASET_FOLDER, exist_ok=True)

# Paths for preloaded PDF and JSON
grc_pdf_path = os.path.join(DATA_FOLDER, 'grc_compliance.pdf')
grc_json_path = os.path.join(DATASET_FOLDER, 'grc_compliance.json')

# Function to chunk text properly
def chunk_text(text, chunk_size=300):
    words = text.split()
    chunks = [' '.join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]
    return chunks

# Preprocess PDF function (converts PDF to JSON chunks)
def preprocess_pdf(pdf_path, json_path, force_refresh=False):
    import fitz  # PyMuPDF
    import time

    if os.path.exists(json_path) and not force_refresh:
        print(f"✅ JSON already exists: {json_path}")
        return

    print(f"⏳ Processing PDF: {pdf_path}...")
    start_time = time.time()
    text_chunks = []

    try:
        with fitz.open(pdf_path) as doc:
            for page_num, page in enumerate(doc):
                text = page.get_text().strip()
                if text:
                    chunks = chunk_text(text)
                    text_chunks.extend(chunks)
                    print(f"📄 Page {page_num + 1}: {len(chunks)} chunks created.")

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(text_chunks, f, ensure_ascii=False, indent=2)

        end_time = time.time()
        print(f"✅ Finished processing: {json_path} (Time: {round(end_time - start_time, 2)} sec)")
        print(f"🔹 Total Chunks Created: {len(text_chunks)}")

    except Exception as e:
        print(f"❌ Error processing PDF {pdf_path}: {e}")

# Load JSON function
def load_json(json_path):
    import json
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Error loading dataset {json_path}: {e}")
        return []

# Preload GRC PDF and JSON
grc_pdf_path = os.path.join(DATA_FOLDER, 'grc_compliance.pdf')
grc_json_path = os.path.join(DATASET_FOLDER, 'grc_compliance.json')

# Initial processing of main PDF if not already processed
if not os.path.exists(grc_json_path):
    preprocess_pdf(grc_pdf_path, grc_json_path)

# Dictionary to hold PDF data
pdf_data = {
    "grc_compliance.pdf": load_json(grc_json_path)
}

# Retrieve relevant text chunks based on user question
def retrieve_relevant_text(question):
    relevant_text = ""
    for pdf_name, chunks in pdf_data.items():
        for chunk in chunks:
            if any(keyword in chunk.lower() for keyword in question.lower().split()):
                relevant_text += f"\n[{pdf_name}] {chunk}\n"
    return relevant_text if relevant_text else "No relevant information found."

# Classify severity level based on response
def classify_severity(response):
    response = response.lower()
    if "critical" in response or "severe" in response:
        return "Extreme High"
    elif "high" in response or "serious" in response:
        return "High"
    elif "moderate" in response or "warning" in response:
        return "Medium"
    else:
        return "Low"
def clear_uploads_and_dataset():
    """
    Deletes all files in the 'uploads' and 'dataset' directories.
    """
    try:
        # Clear uploaded files
        for filename in os.listdir(UPLOAD_FOLDER):
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
        
        # Clear dataset JSON files
        for filename in os.listdir(DATASET_FOLDER):
            file_path = os.path.join(DATASET_FOLDER, filename)
            if filename.endswith('.json') and os.path.isfile(file_path):
                os.remove(file_path)

        print("✅ Uploads and dataset folder cleared.")
    except Exception as e:
        print(f"❌ Error clearing uploads or dataset folder: {e}")

@app.route('/end_session', methods=['POST'])
def end_session():
    clear_uploads_and_dataset()
    return jsonify({"message": "✅ Session ended. All uploaded files and dataset JSON files were deleted."})

@app.route('/start_new_session', methods=['POST'])
def start_new_session():
    clear_uploads_and_dataset()
    return jsonify({"message": "✅ New session started. Page will reload."})

# Query Llama3 function
def ask_llama(question):
    import ollama

    context = retrieve_relevant_text(question)
    prompt = f"""
    You are a cybersecurity assistant specialized in Governance, Risk, and Compliance (GRC).
    Answer questions using the provided document context. If the question is unrelated, politely refuse to answer.
    Also, classify the severity of the issue as Low, Medium, High, or Extreme High.

    Context:
    {context}

    Question: {question}

    Answer:
    """
    response = ollama.chat(model='llama3', messages=[{"role": "user", "content": prompt}])
    answer_text = response["message"]["content"]
    severity = classify_severity(answer_text)
    
    return {"answer": answer_text, "severity": severity}

from flask import request, render_template, jsonify


@app.route('/ask', methods=['POST'])
def ask():
    data = request.json
    question = data.get('question', '').strip()
    if not question:
        return jsonify({"error": "No question provided"}), 400
    
    response_data = ask_llama(question)
    return jsonify(response_data)

@app.route('/upload', methods=['POST'])
def upload_pdf():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    # JSON path for newly uploaded file
    new_json_path = os.path.join(DATASET_FOLDER, f"{file.filename}.json")

    print(f"⏳ Uploading {file.filename}...")

    try:
        preprocess_pdf(filepath, new_json_path)
        pdf_data[file.filename] = load_json(new_json_path)
        return jsonify({"message": f"✅ Upload Complete! {file.filename} processed."})

    except Exception as e:
        print(f"❌ Processing failed: {str(e)}")
        return jsonify({"error": f"Processing failed: {str(e)}"}), 500

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')  # ✅ Fix UnicodeEncodeError on Windows
    app.run(debug=True)