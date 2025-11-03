import os, time

from google.cloud import vision, storage

PROJECT_ID = os.getenv("GCP_PROJECT_ID")
BUCKET = os.getenv("GCS_BUCKET")

def upload_to_gcs(local_path: str, dest_name: str):
    client = storage.Client(project=PROJECT_ID)
    bucket = client.bucket(BUCKET)
    blob = bucket.blob(dest_name)
    blob.upload_from_filename(local_path)
    return f"gs://{BUCKET}/{dest_name}"

# For PDFs/TIFFs (async batch)
def ocr_pdf_to_text_gcs(gcs_uri: str) -> str:
    client = vision.ImageAnnotatorClient()
    mime_type = "application/pdf"
    feature = vision.types.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)
    gcs_source = vision.types.GcsSource(uri=gcs_uri)
    gcs_destination = vision.types.GcsDestination(uri=gcs_uri + ".out/")
    input_config = vision.types.InputConfig(gcs_source=gcs_source, mime_type=mime_type)
    output_config = vision.types.OutputConfig(gcs_destination=gcs_destination, batch_size=25)
    async_request = vision.types.AsyncAnnotateFileRequest(
        features=[feature],
        input_config=input_config,
        output_config=output_config
    )
    operation = client.async_batch_annotate_files(requests=[async_request])
    operation.result(timeout=600)
    # Download the first output JSON
    storage_client = storage.Client()
    bucket_name = gcs_uri.split("/")[2]
    prefix = "/".join(gcs_uri.split("/")[3:]) + ".out/"
    bucket = storage_client.bucket(bucket_name)
    blobs = list(bucket.list_blobs(prefix=prefix))
    texts = []
    for b in blobs:
        if b.name.endswith(".json"):
            data = b.download_as_bytes()
            # Each JSON has fullTextAnnotation / textAnnotations
            import json
            j = json.loads(data.decode())
            for resp in j.get("responses", []):
                ann = resp.get("fullTextAnnotation", {})
                if ann.get("text"): texts.append(ann["text"])
    return "\n".join(texts)

# For images (sync)
def ocr_image_local(path: str) -> str:
    client = vision.ImageAnnotatorClient()
    with open(path, "rb") as f:
        content = f.read()
    image = vision.Image(content=content)
    resp = client.document_text_detection(image=image)
    return resp.full_text_annotation.text or ""
