import pdfplumber
import pytesseract
from PIL import Image
import spacy
from spacy.training.example import Example


# Step 1: Extract text from PDF
def extract_text_from_pdf(pdf_path):
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    return text


# Step 2: Extract text from image
def extract_text_from_image(image_path):
    return pytesseract.image_to_string(Image.open(image_path))


# Step 3: Train a spaCy model with labeled examples
def train_spacy_model(train_data):
    nlp = spacy.blank("en")
    ner = nlp.add_pipe("ner")

    # Add labels
    for _, annotations in train_data:
        for ent in annotations.get("entities"):
            ner.add_label(ent[2])

    optimizer = nlp.initialize()

    for epoch in range(20):
        losses = {}
        for text, annotations in train_data:
            example = Example.from_dict(nlp.make_doc(text), annotations)
            nlp.update([example], sgd=optimizer, losses=losses)
        print(f"Epoch {epoch} Losses: {losses}")

    return nlp


# Step 4: Example usage
if __name__ == "__main__":
    # Example labeled training data: (text, {"entities": [(start, end, label)]})
    training_data = [
        ("Invoice number: 12345 Date: 2024-05-10 Total: $450",
         {"entities": [(15, 20, "INVOICE"), (27, 37, "DATE"), (46, 50, "TOTAL")]}),
        ("Invoice 99887 issued on 2025-09-01 amounting to $1200",
         {"entities": [(8, 13, "INVOICE"), (25, 35, "DATE"), (49, 54, "TOTAL")]})
    ]

    # Train the model
    nlp_model = train_spacy_model(training_data)

    # Load a PDF or image
    pdf_text = extract_text_from_pdf("sample_invoice.pdf")
    image_text = extract_text_from_image("invoice_image.png")

    # Run model
    for doc_text in [pdf_text, image_text]:
        doc = nlp_model(doc_text)
        for ent in doc.ents:
            print(ent.label_, ":", ent.text)