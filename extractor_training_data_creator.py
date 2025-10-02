# Code needs to sort through the existing Orders database, download the source file, determine if the source file is a text pdf or an image pdf
import pdfplumber
from pdf2image import convert_from_path
import pytesseract
import fitz  # PyMuPDF
from PIL import Image

# --- Step 1: Detect PDF type ---
def detect_pdf_type(pdf_path):
    doc = fitz.open(pdf_path)
    has_text, has_images = False, False

    for page in doc:
        if page.get_text().strip():
            has_text = True
        if page.get_images():
            has_images = True

    if has_text and not has_images:
        return "text-pdf"
    elif not has_text and has_images:
        return "image-pdf"
    elif has_text and has_images:
        return "hybrid-pdf"
    else:
        return "empty-pdf"


# --- Step 2: Extract text from text-PDF ---
def extract_text_pdf(pdf_path):
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text


# --- Step 3: Extract text from image-PDF (OCR) ---
def extract_ocr_pdf(pdf_path, dpi=300):
    images = convert_from_path(pdf_path, dpi=dpi)
    text = ""
    for i, img in enumerate(images):
        page_text = pytesseract.image_to_string(img, lang="eng")
        text += f"\n--- Page {i+1} ---\n{page_text}"
    return text


# --- Step 4: Unified Extractor ---
def extract_text_auto(pdf_path):
    pdf_type = detect_pdf_type(pdf_path)
    print(f"Detected type: {pdf_type}")

    if pdf_type == "text-pdf":
        return extract_text_pdf(pdf_path)

    elif pdf_type == "image-pdf":
        return extract_ocr_pdf(pdf_path)

    elif pdf_type == "hybrid-pdf":
        # Try text first, then OCR if needed
        text = extract_text_pdf(pdf_path)
        ocr_text = extract_ocr_pdf(pdf_path)
        return text + "\n[OCR-Fallback]\n" + ocr_text

    else:
        return ""

def search_find(text, search_str):
    start_index = text.find(search_str)
    if start_index != -1:
        end_index = start_index + len(search_str) - 1
        print(f"Match found from {start_index} to {end_index}")
        return 1, start_index, end_index
    else:
        print("No match found")
        return 0, -1, -1


# --- Example Usage ---
if __name__ == "__main__":
    training_data = []
    tuple_labels = []
    pdf_file = "training/test.pdf"
    text = extract_text_auto(pdf_file)
    text_cap = text.upper()
    print(text[:1000])  # print first 1000 chars
    # Next need to save the text and each label in a csv format:
    # with start and end  for each label defining where it is located in the text
    # Each row of corresponds to one entity
    # Only annotate labels that actually exist in the text.
    labels = ['Container', 'BOL', 'Booking', 'Shipper']
    knowns = ['BSIU9719610', 'NGB20230762', None, 'Four Seasons Trading']
    for kx,label in enumerate(labels):
        test = knowns[kx]
        if test is not None:
            result, start, stop = search_find(text_cap, test.upper())
            if result == 1:
                tuple_labels.append((start,stop,label))
    training_data.append((text,{'entities':tuple_labels}))
    print(training_data)

    #Now write the training data out to a file:
    import csv

    with open("training/training_data.csv", "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["text", "start", "end", "label"])  # header
        for text, annotations in training_data:
            #print(f'the annotations are: {annotations}')
            for start, end, label in annotations["entities"]:
                #print(f'start end label are: {start}, {end}, {label}')
                writer.writerow([text, start, end, label])

