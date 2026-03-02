#!/usr/bin/env python3
"""
Documentation collector script for market prediction APIs and data sources
Fetches documentation from multiple sources and organizes them for indexing
"""

import os
import requests
from urllib.parse import urljoin, urlparse
from pathlib import Path
import json
import time
from datetime import datetime
from bs4 import BeautifulSoup
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DocCollector:
    def __init__(self, base_dir='docs'):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
    def fetch_page(self, url, timeout=10):
        """Fetch a single page with error handling"""
        try:
            logger.info(f"Fetching: {url}")
            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching {url}: {e}")
            return None
    
    def save_content(self, content, filepath):
        """Save content to a file"""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info(f"Saved: {filepath}")
    
    def extract_links(self, html, base_url):
        """Extract all links from HTML content"""
        soup = BeautifulSoup(html, 'html.parser')
        links = set()
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            # Convert relative URLs to absolute
            absolute_url = urljoin(base_url, href)
            # Only keep links from the same domain
            if urlparse(absolute_url).netloc == urlparse(base_url).netloc:
                # Remove fragments
                absolute_url = absolute_url.split('#')[0]
                if absolute_url.endswith(('html', '/', '')):
                    links.add(absolute_url)
        
        return links
    
    def collect_polymarket(self):
        """Collect Polymarket documentation"""
        logger.info("=" * 60)
        logger.info("Collecting Polymarket docs...")
        logger.info("=" * 60)
        
        base_url = "https://docs.polymarket.com/"
        folder = self.base_dir / "polymarket"
        folder.mkdir(exist_ok=True)
        
        try:
            # Fetch main docs page
            html = self.fetch_page(base_url)
            if html:
                self.save_content(html, folder / "index.html")
                
                # Extract and fetch linked pages
                links = self.extract_links(html, base_url)
                for link in list(links)[:20]:  # Limit to 20 pages
                    if link != base_url:
                        page_html = self.fetch_page(link)
                        if page_html:
                            # Create a filename from the URL
                            path = urlparse(link).path.strip('/')
                            filename = path.replace('/', '_') + '.html' if path else 'page.html'
                            self.save_content(page_html, folder / filename)
                        time.sleep(0.5)  # Rate limiting
        except Exception as e:
            logger.error(f"Error collecting Polymarket docs: {e}")
    
    def collect_kalshi(self):
        """Collect Kalshi documentation"""
        logger.info("=" * 60)
        logger.info("Collecting Kalshi docs...")
        logger.info("=" * 60)
        
        base_url = "https://docs.kalshi.com/welcome"
        folder = self.base_dir / "kalshi"
        folder.mkdir(exist_ok=True)
        
        try:
            html = self.fetch_page(base_url)
            if html:
                self.save_content(html, folder / "index.html")
                
                # Extract and fetch linked documentation pages
                links = self.extract_links(html, "https://docs.kalshi.com/")
                for link in list(links)[:20]:
                    if link != base_url:
                        page_html = self.fetch_page(link)
                        if page_html:
                            path = urlparse(link).path.strip('/')
                            filename = path.replace('/', '_') + '.html' if path else 'page.html'
                            self.save_content(page_html, folder / filename)
                        time.sleep(0.5)
        except Exception as e:
            logger.error(f"Error collecting Kalshi docs: {e}")
    
    def collect_metaculus(self):
        """Collect Metaculus API documentation"""
        logger.info("=" * 60)
        logger.info("Collecting Metaculus API docs...")
        logger.info("=" * 60)
        
        base_url = "https://www.metaculus.com/api/"
        folder = self.base_dir / "metaculus"
        folder.mkdir(exist_ok=True)
        
        try:
            html = self.fetch_page(base_url)
            if html:
                self.save_content(html, folder / "api.html")
                
                # Try to fetch API schema if available
                schema_url = "https://www.metaculus.com/api/schema/"
                schema = self.fetch_page(schema_url)
                if schema:
                    self.save_content(schema, folder / "schema.html")
        except Exception as e:
            logger.error(f"Error collecting Metaculus docs: {e}")
    
    def collect_fred(self):
        """Collect FRED documentation"""
        logger.info("=" * 60)
        logger.info("Collecting FRED docs...")
        logger.info("=" * 60)
        
        base_url = "https://fred.stlouisfed.org/"
        folder = self.base_dir / "fred"
        folder.mkdir(exist_ok=True)
        
        try:
            # Fetch main page
            html = self.fetch_page(base_url)
            if html:
                self.save_content(html, folder / "index.html")
            
            # Fetch API documentation
            api_docs = [
                "https://fred.stlouisfed.org/docs/api/",
                "https://fred.stlouisfed.org/docs/api/fred/",
            ]
            
            for api_url in api_docs:
                html = self.fetch_page(api_url)
                if html:
                    filename = urlparse(api_url).path.strip('/').replace('/', '_') + '.html'
                    self.save_content(html, folder / filename)
                time.sleep(0.5)
        except Exception as e:
            logger.error(f"Error collecting FRED docs: {e}")
    
    def collect_alphavantage(self):
        """Collect Alpha Vantage documentation"""
        logger.info("=" * 60)
        logger.info("Collecting Alpha Vantage docs...")
        logger.info("=" * 60)
        
        base_url = "https://www.alphavantage.co/"
        folder = self.base_dir / "alphavantage"
        folder.mkdir(exist_ok=True)
        
        try:
            html = self.fetch_page(base_url)
            if html:
                self.save_content(html, folder / "index.html")
            
            # Try common documentation pages
            docs_urls = [
                "https://www.alphavantage.co/documentation/",
                "https://www.alphavantage.co/apis",
            ]
            
            for url in docs_urls:
                html = self.fetch_page(url)
                if html:
                    filename = urlparse(url).path.strip('/').replace('/', '_') + '.html'
                    self.save_content(html, folder / filename)
                time.sleep(0.5)
        except Exception as e:
            logger.error(f"Error collecting Alpha Vantage docs: {e}")
    
    def collect_sec(self):
        """Collect SEC search and filings documentation"""
        logger.info("=" * 60)
        logger.info("Collecting SEC docs...")
        logger.info("=" * 60)
        
        base_url = "https://www.sec.gov/search-filings"
        folder = self.base_dir / "sec"
        folder.mkdir(exist_ok=True)
        
        try:
            html = self.fetch_page(base_url)
            if html:
                self.save_content(html, folder / "search-filings.html")
            
            # Fetch related documentation
            sec_urls = [
                "https://www.sec.gov/cgi-bin/browse-edgar",
                "https://www.sec.gov/edgar/how-to-use-edgar.html",
            ]
            
            for url in sec_urls:
                html = self.fetch_page(url)
                if html:
                    filename = urlparse(url).path.strip('/').replace('/', '_') + '.html'
                    self.save_content(html, folder / filename)
                time.sleep(0.5)
        except Exception as e:
            logger.error(f"Error collecting SEC docs: {e}")
    
    def create_index(self):
        """Create a summary index of collected documentation"""
        logger.info("=" * 60)
        logger.info("Creating index...")
        logger.info("=" * 60)
        
        index = {
            "timestamp": datetime.now().isoformat(),
            "sources": []
        }
        
        # Walk through all folders and collect info
        for source_dir in self.base_dir.iterdir():
            if source_dir.is_dir():
                files = list(source_dir.glob('**/*.html'))
                index["sources"].append({
                    "name": source_dir.name,
                    "file_count": len(files),
                    "files": [str(f.relative_to(self.base_dir)) for f in files]
                })
        
        # Save index as JSON
        index_file = self.base_dir / "INDEX.json"
        with open(index_file, 'w') as f:
            json.dump(index, f, indent=2)
        logger.info(f"Index saved: {index_file}")
        
        # Also create a markdown summary
        md_file = self.base_dir / "README.md"
        with open(md_file, 'w') as f:
            f.write("# Documentation Collection\n\n")
            f.write(f"Collected: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("## Sources\n\n")
            for source in index["sources"]:
                f.write(f"### {source['name']}\n")
                f.write(f"Files collected: {source['file_count']}\n\n")
                for file in sorted(source['files'])[:5]:
                    f.write(f"- {file}\n")
                if len(source['files']) > 5:
                    f.write(f"- ... and {len(source['files']) - 5} more files\n")
                f.write("\n")
        logger.info(f"README created: {md_file}")
    
    def collect_all(self):
        """Collect documentation from all sources"""
        logger.info("Starting documentation collection...")
        start_time = time.time()
        
        self.collect_polymarket()
        time.sleep(1)
        
        self.collect_kalshi()
        time.sleep(1)
        
        self.collect_metaculus()
        time.sleep(1)
        
        self.collect_fred()
        time.sleep(1)
        
        self.collect_alphavantage()
        time.sleep(1)
        
        self.collect_sec()
        time.sleep(1)
        
        self.create_index()
        
        elapsed = time.time() - start_time
        logger.info("=" * 60)
        logger.info(f"Documentation collection completed in {elapsed:.2f} seconds")
        logger.info("=" * 60)

if __name__ == "__main__":
    collector = DocCollector(base_dir='docs')
    collector.collect_all()
