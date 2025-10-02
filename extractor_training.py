import json
import pdfplumber
import pytesseract
from PIL import Image
import spacy
from spacy.training.example import Example


# Step 1: Load training data from JSON
def load_training_data(json_path):
    with open(json_path, "r") as f:
        data = json.load(f)
    return [(item["text"], {"entities": item["entities"]}) for item in data]


# Step 2: Train spaCy NER model
def train_spacy_model(train_data, n_iter=20):
    nlp = spacy.blank("en")
    ner = nlp.add_pipe("ner")

    # Add labels
    for _, annotations in train_data:
        for ent in annotations.get("entities"):
            ner.add_label(ent[2])

    optimizer = nlp.initialize()

    for epoch in range(n_iter):
        losses = {}
        for text, annotations in train_data:
            example = Example.from_dict(nlp.make_doc(text), annotations)
            nlp.update([example], sgd=optimizer, losses=losses)
        print(f"Epoch {epoch + 1}/{n_iter} Losses: {losses}")

    return nlp


# Step 3: Extract text from PDF
def extract_text_from_pdf(pdf_path):
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text


# Step 4: Extract text from Image
def extract_text_from_image(image_path):
    return pytesseract.image_to_string(Image.open(image_path))


# Step 5: Run model on new documents
def extract_entities_from_doc(nlp_model, text):
    doc = nlp_model(text)
    return [(ent.label_, ent.text) for ent in doc.ents]


if __name__ == "__main__":
    # Load and train
    training_data = load_training_data("training_data.json")
    nlp_model = train_spacy_model(training_data, n_iter=30)

    # Save the model for reuse
    nlp_model.to_disk("invoice_model")

    # Example: Extract from PDF
    pdf_text = extract_text_from_pdf("sample_invoice.pdf")
    print("From PDF:", extract_entities_from_doc(nlp_model, pdf_text))

    # Example: Extract from Image
    img_text = extract_text_from_image("invoice_image.png")
    print("From Image:", extract_entities_from_doc(nlp_model, img_text))
