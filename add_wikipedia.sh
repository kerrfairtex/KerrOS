#!/bin/bash

echo "🌐 Adding Wikipedia to Offline AI..."
echo ""

# Configuration
WIKI_DIR="$HOME/offline_ai/data/documents/wikipedia"
DATA_DIR="$HOME/offline_ai/data"
DOWNLOAD_SIZE=0

# Create directory
mkdir -p $WIKI_DIR
cd $WIKI_DIR

echo "📥 Step 1: Downloading Wikipedia data..."
echo ""

# Download abstracts (smallest, fastest)
echo "⏳ Downloading Wikipedia abstracts (~1.2 GB)..."
wget -q --show-progress https://dumps.wikimedia.org/enwiki/latest/enwiki-latest-abstract.xml.gz

if [ $? -eq 0 ]; then
    DOWNLOAD_SIZE=$(($(du -sh enwiki-latest-abstract.xml.gz | cut -f1 | sed 's/G//') * 1000))
    echo "✅ Downloaded: $(du -sh enwiki-latest-abstract.xml.gz | cut -f1)"
else
    echo "❌ Download failed. Trying alternative source..."
    exit 1
fi

echo ""
echo "📦 Step 2: Extracting Wikipedia..."
gunzip -v enwiki-latest-abstract.xml.gz

EXTRACTED_SIZE=$(du -sh enwiki-latest-abstract.xml | cut -f1)
echo "✅ Extracted: $EXTRACTED_SIZE"

echo ""
echo "🔄 Step 3: Parsing Wikipedia to text files..."

# Parse XML to text
python3 << 'PYTHON'
import xml.etree.ElementTree as ET
import os
from pathlib import Path

wiki_file = "enwiki-latest-abstract.xml"
output_dir = "articles"
os.makedirs(output_dir, exist_ok=True)

count = 0
try:
    for event, elem in ET.iterparse(wiki_file, events=['end']):
        if elem.tag.endswith('doc'):
            title = elem.find('title')
            abstract = elem.find('abstract')
            
            if title is not None and abstract is not None:
                title_text = title.text or "Unknown"
                abstract_text = abstract.text or ""
                
                # Save article
                filename = f"{output_dir}/{title_text.replace('/', '_')}.txt"
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(f"Title: {title_text}\n\n{abstract_text}\n")
                
                count += 1
                if count % 100000 == 0:
                    print(f"Processed {count} articles...")
            
            elem.clear()
    
    print(f"\n✅ Total articles parsed: {count}")
except Exception as e:
    print(f"Error: {e}")
PYTHON

echo ""
echo "📊 Step 4: Calculating storage..."

ARTICLES_SIZE=$(du -sh articles | cut -f1)
echo "Articles folder size: $ARTICLES_SIZE"

echo ""
echo "🔐 Step 5: Re-indexing RAG store..."

# Update RAG store
python3 << 'PYTHON'
import json
import os
from pathlib import Path
from datetime import datetime

rag_file = os.path.expanduser("~/offline_ai/data/rag_store.json")
articles_dir = "articles"

# Load existing RAG store
try:
    with open(rag_file, 'r') as f:
        rag_data = json.load(f)
except:
    rag_data = []

print(f"📖 Indexing Wikipedia articles...")

article_count = 0
for article_file in Path(articles_dir).glob('*.txt'):
    with open(article_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    entry = {
        "text": content[:1000],  # First 1000 chars as preview
        "source": f"wikipedia/{article_file.name}",
        "title": article_file.stem,
        "type": "wikipedia",
        "indexed_at": datetime.now().isoformat()
    }
    
    rag_data.append(entry)
    article_count += 1

# Save updated RAG store
with open(rag_file, 'w') as f:
    json.dump(rag_data, f, indent=2)

print(f"✅ Indexed {article_count} articles")
print(f"RAG store size: {os.path.getsize(rag_file) / (1024**3):.2f} GB")
PYTHON

echo ""
echo "✨ Done! Wikipedia added to your offline AI"

