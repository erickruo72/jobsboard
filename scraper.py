import requests
from bs4 import BeautifulSoup
import time
import json
import os
import sqlite3
from requests.auth import HTTPBasicAuth
from openai import OpenAI

# -----------------------
# Configuration
# -----------------------
BASE_URL = "https://www.myjobmag.co.ke"
START_URL = f"{BASE_URL}/jobs-by-date/today"

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}

# Use environment variables for sensitive data
WP_API_URL = os.environ.get("WP_API_URL")
WP_USER = os.environ.get("WP_USER")
WP_PASS = os.environ.get("WP_PASS")

CACHE_FILE = "apply_url_cache.json"
REQUEST_TIMEOUT = 15

# -----------------------
# OpenAI Setup
# -----------------------
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# -----------------------
# Database Functions
# -----------------------
def init_db():
    conn = sqlite3.connect('posted_jobs.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS posted_jobs (
            job_id TEXT PRIMARY KEY
        )
    ''')
    conn.commit()
    conn.close()

def is_job_posted(job_id: str) -> bool:
    conn = sqlite3.connect('posted_jobs.db')
    c = conn.cursor()
    c.execute("SELECT 1 FROM posted_jobs WHERE job_id=?", (job_id,))
    exists = c.fetchone() is not None
    conn.close()
    return exists

def mark_job_as_posted(job_id: str):
    conn = sqlite3.connect('posted_jobs.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO posted_jobs (job_id) VALUES (?)", (job_id,))
    conn.commit()
    conn.close()

# -----------------------
# Helper Functions
# -----------------------
def get_soup(url: str) -> BeautifulSoup:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"❌ Failed to get page {url}: {e}")
        return None

def clean_description(desc_block: BeautifulSoup) -> str:
    if not desc_block:
        return ""
    
    # Remove original ul block
    original_ul = desc_block.find("ul", class_="job-key-info")
    if original_ul:
        original_ul.decompose()

    # The rest of your cleaning logic
    for a in desc_block.select("a[href^='/cv'], a.view-all2"):
        if a['href'] == '/cv' and a.parent:
            a.parent.decompose()
        else:
            a.decompose()
    for selector in ["#adbox", "form.read-sub-form-top", "#read-in-ad"]:
        for tag in desc_block.select(selector):
            tag.decompose()
    for p in desc_block.select("p"):
        if "Never pay for any CBT" in p.get_text():
            p.decompose()

    return desc_block.decode_contents(formatter="html")


def resolve_apply_link(job_url: str) -> str:
    try:
        resp = requests.get(job_url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        return resp.url
    except Exception as e:
        print(f"❌ Failed to resolve apply link for {job_url}: {e}")
        return job_url

# -----------------------
# AI Rewrite Functions
# -----------------------
def rewrite_job_title(original_title: str) -> str:
    try:
        prompt = f"""
Rewrite this job title for SEO without changing its core meaning.

Original Title: {original_title}

- Keep the structure similar to a standard job posting.
- Do NOT add any marketing phrases like 'Join Our Team!', 'Apply Now!', 'Exciting Opportunity,' 'Urgent Hire,' 'We're Hiring,' or similar words in parentheses.
- Keep it concise and professional.
- The output should be the clean title, nothing more.
"""
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            timeout=20
        )
        new_title = resp.choices[0].message.content.strip()
        unwanted_phrases = ["(Join Our Team!)", "(Exciting Opportunity)", "(Urgent Hire)", "(Apply Now!)"]
        for phrase in unwanted_phrases:
            new_title = new_title.replace(phrase, "").strip()
        return new_title.strip(" -")
    except Exception as e:
        print(f"⚠️ Title rewrite failed: {e}")
        return original_title

def rewrite_job_description(raw_html: str) -> str:
    try:
        prompt = f"""
Rewrite the following job description professionally and clearly.
- Preserve all HTML tags: <p>, <b>, <ul>, <li>.
- Keep Job Type, Qualification, Experience, Location, Job Field, Posted/Deadline unchanged.
- Improve clarity, readability, and SEO.
- Do not add markdown, asterisks, or extra labels.

Job Description:
{raw_html}
"""
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            timeout=30
        )
        rewritten_html = resp.choices[0].message.content.strip()
        return rewritten_html
    except Exception as e:
        print(f"⚠️ Description rewrite failed: {e}")
        return raw_html

def generate_standout_tips(job_title: str, field: str, qualification: str) -> str:
    try:
        prompt = f"""
Generate 3-5 short, practical tips for applicants on how to stand out when applying for this job:

Job Title: {job_title}
Field: {field}
Qualification: {qualification}

- Write in HTML <ul><li> format.
- Keep each tip clear and professional.
- Do not include introductions or conclusions, just the list.
"""
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            timeout=20
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️ Standout tips generation failed: {e}")
        return ""

def rewrite_excerpt(original_excerpt: str) -> str:
    try:
        prompt = f"""
Write a concise, factual, and SEO-friendly meta description (under 160 characters) for this job.
The description should clearly state the company, job title, and location.

Original Excerpt: {original_excerpt}

- Do NOT use marketing phrases like 'Join us,' 'Kickstart your career,' 'Exciting opportunity,' or calls to action like 'Apply today!'
- The output should be a simple, factual statement that a search engine can use.
"""
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            timeout=20
        )
        new_excerpt = resp.choices[0].message.content.strip()
        return new_excerpt
    except Exception as e:
        print(f"⚠️ Excerpt rewrite failed: {e}")
        return original_excerpt

# -----------------------
# URL Slug Generator
# -----------------------
def slugify(text: str) -> str:
    return text.replace(" ", "-").replace("/", "-").replace(",", "").replace(".", "").lower()

# -----------------------
# Parse Job
# -----------------------
def parse_job(job_url: str) -> dict:
    soup = get_soup(job_url)
    if not soup:
        return None, None, None

    job_data = {"url": job_url}

    # Title
    title_tag = soup.select_one("h1")
    original_title = title_tag.get_text(strip=True) if title_tag else "Untitled Job"
    job_data["title"] = rewrite_job_title(original_title)

    # Dates
    posted_date_tag = soup.select_one("#posted-date")
    deadline_tag = soup.select_one("div.read-date-sec-li:not(#posted-date)")
    job_data["posted_date"] = (
        posted_date_tag.get_text(strip=True).replace("Posted:", "").strip()
        if posted_date_tag else "Not specified"
    )
    job_data["deadline_date"] = (
        deadline_tag.get_text(strip=True).replace("Deadline:", "").strip()
        if deadline_tag else "Not specified"
    )

    # Job Key Info - Find the original ul for data extraction
    job_key_ul = soup.select_one("ul.job-key-info")
    job_info = {}
    job_key_ul_content = ""
    
    if job_key_ul:
        for li in job_key_ul.select("li"):
            key_tag = li.select_one("span.jkey-title")
            value_span = li.select_one("span.jkey-info")
            if key_tag and value_span:
                key = key_tag.get_text(strip=True).rstrip(":")
                val_text = value_span.get_text(strip=True)
                job_info[key] = val_text
        
        # Now, create a new HTML string for the job info list with dynamic links
        job_key_ul_content = "<ul>"
        for key, val in job_info.items():
            job_key_ul_content += f"<li><span class='jkey-title'>{key}:</span> "
            if key == "Job Type":
                link_slug = slugify(val)
                job_key_ul_content += f"<a href='{BASE_URL}/jobs-by-type/{link_slug}'>{val}</a>"
            elif key == "Location":
                link_slug = slugify(val)
                job_key_ul_content += f"<a href='{BASE_URL}/jobs-location/{link_slug}'>{val}</a>"
            elif key == "Job Field":
                fields = [f.strip() for f in val.split("/")]
                links = [f"<a href='{BASE_URL}/jobs-by-field/{slugify(f)}'>{f}</a>" for f in fields]
                job_key_ul_content += " / ".join(links)
            elif key == "Qualification":
                link_slug = slugify(val)
                job_key_ul_content += f"<a href='{BASE_URL}/jobs-by-education/{link_slug}'>{val}</a>"
            elif key == "Experience":
                link_slug = slugify(val)
                job_key_ul_content += f"<a href='{BASE_URL}/jobs-by-experience/{link_slug}'>{val}</a>"
            else:
                job_key_ul_content += val
            job_key_ul_content += "</li>"
        job_key_ul_content += "</ul>"

    # Job Description
    desc_block = soup.select_one("li.job-description")
    
    # Extract the first paragraph as the company overview
    company_desc_with_title = ""
    if desc_block:
        first_p = desc_block.find("p")
        if first_p:
            company_desc_with_title = f"<h2>Company Overview</h2>{first_p}"
            first_p.decompose() # Remove it from the original block

    job_description = clean_description(desc_block)

    description_with_dates = (
        f"<p><b>Posted:</b> {job_data['posted_date']}&emsp;&emsp;<b>Deadline:</b> {job_data['deadline_date']}</p>"
    )
    
    # Combine all parts in the correct order
    full_description = f"{description_with_dates}{job_key_ul_content}{company_desc_with_title}{job_description}"
    job_data["description"] = rewrite_job_description(full_description)
    
    # Generate "How to Stand Out" section
    job_title = job_data["title"]
    field = job_info.get("Job Field", "")
    qualification = job_info.get("Qualification", "")
    standout_tips = generate_standout_tips(job_title, field, qualification)
    if standout_tips:
        job_data["description"] += "<h2>How to Stand Out for This Job</h2>" + standout_tips

    # Generate Categories and Tags (for API payload, not internal HTML)
    categories = []
    tags = []
    
    job_type = job_info.get("Job Type", "")
    if job_type:
        categories.append(f"{job_type} Jobs")
        tags.append(f"{job_type} Jobs")

    qualification = job_info.get("Qualification", "")
    if qualification:
        tags.append(f"{qualification} Jobs")
    
    experience = job_info.get("Experience", "")
    if experience:
        tags.append(f"{experience} experience Jobs")

    location = job_info.get("Location", "")
    if location:
        categories.append(f"Jobs in {location}")
        tags.append(f"{location} Jobs")

    job_field = job_info.get("Job Field", "")
    if job_field:
        fields = [f.strip() for f in job_field.split("/")]
        if fields:
            categories.append(f"{fields[0]} Jobs")
            tags.extend([f"{f} Jobs" for f in fields])
    
    job_data["categories"] = list(dict.fromkeys(categories))
    job_data["tags"] = list(dict.fromkeys(tags))
    
    job_data["job_type"] = job_type
    job_data["qualification"] = qualification
    job_data["job_field"] = job_field
    job_data["location"] = location

    # Excerpt - now with AI rewrite
    company = "Unknown Company"
    if " at " in original_title:
        parts = original_title.split(" at ")
        job_title_for_excerpt = parts[0].strip()
        company = parts[1].strip()
    else:
        job_title_for_excerpt = original_title
    
    original_excerpt = f"{company} is hiring a {job_title_for_excerpt} in {location}."
    job_data["excerpt"] = rewrite_excerpt(original_excerpt)

    # Apply link
    apply_tag = soup.select_one("a[href^='/apply-now/']")
    if apply_tag:
        apply_url = BASE_URL + apply_tag["href"]
        resolved_url = resolve_apply_link(apply_url)
        job_data["apply_url"] = resolved_url
        job_id = apply_tag["href"].split("/")[-1]
        return job_data, job_id, resolved_url

    return job_data, None, None

# -----------------------
# WordPress Helper
# -----------------------
def get_wp_term_id(name: str, taxonomy: str):
    try:
        url = f"https://opportunee.com/wp-json/wp/v2/{taxonomy}?search={name}"
        resp = requests.get(url, auth=HTTPBasicAuth(WP_USER, WP_PASS), timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            for term in resp.json():
                if term.get("name").lower() == name.lower():
                    return term.get("id")
        create_resp = requests.post(f"https://opportunee.com/wp-json/wp/v2/{taxonomy}",
                                     auth=HTTPBasicAuth(WP_USER, WP_PASS),
                                     json={"name": name},
                                     timeout=REQUEST_TIMEOUT)
        if create_resp.status_code in [200, 201]:
            return create_resp.json().get("id")
        return None
    except Exception as e:
        print(f"❌ Exception while handling {taxonomy} '{name}': {e}")
        return None

def post_to_wordpress(job: dict) -> bool:
    try:
        category_ids = [get_wp_term_id(c, "categories") for c in job.get("categories", []) if c.strip()]
        tag_ids = [get_wp_term_id(t, "tags") for t in job.get("tags", []) if t.strip()]
        
        payload = {
            "title": job["title"],
            "content": job["description"],
            "excerpt": job.get("excerpt", ""),
            "status": "publish",
            "categories": [c_id for c_id in category_ids if c_id],
            "tags": [t_id for t_id in tag_ids if t_id],
        }
        response = requests.post(WP_API_URL, auth=HTTPBasicAuth(WP_USER, WP_PASS),
                                 json=payload, timeout=REQUEST_TIMEOUT)
        if response.status_code == 201:
            print(f"✅ Posted with categories: {job['categories']} and tags: {job['tags']}")
            return True
        print(f"❌ Failed to post {job['title']}: {response.status_code} {response.text}")
        return False
    except Exception as e:
        print(f"❌ Exception posting job {job['title']}: {e}")
        return False

# -----------------------
# Main Scraper
# -----------------------
if __name__ == "__main__":
    all_success = 0
    all_failed = 0
    page = 1
    cache = {}
    init_db()  # Initialize the database here

    while True:
        url = f"{BASE_URL}/jobs-by-date/today/{page}" if page > 1 else START_URL
        print(f"\n🔎 Scraping Page {page}: {url}")
        soup = get_soup(url)
        if not soup:
            print(f"❌ Skipping page {page} due to load failure.")
            break

        job_links = [BASE_URL + a["href"] for a in soup.select("h2 a[href^='/job/']")]
        if not job_links:
            print("📌 No more jobs found. Ending scraping.")
            break

        print(f"📄 Found {len(job_links)} jobs on this page.")

        for idx, link in enumerate(job_links, 1):
            print(f"   → Scraping Job {idx}/{len(job_links)}: {link}")
            job_data, job_id, resolved_url = parse_job(link)
            
            if not job_id:
                print(f"❌ Failed to get job ID for {link}. Skipping.")
                all_failed += 1
                continue

            if is_job_posted(job_id):
                print(f"   → Job ID {job_id} already posted. Skipping.")
                continue

            if not job_data:
                print(f"❌ Failed to parse job {link}")
                all_failed += 1
                continue

            if job_id and resolved_url:
                cache[job_id] = resolved_url

            if post_to_wordpress(job_data):
                all_success += 1
                mark_job_as_posted(job_id) # Mark as posted on success
            else:
                all_failed += 1

        page += 1
        time.sleep(2)

    if cache:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
        print(f"\n💾 Updated apply URL cache: {CACHE_FILE}")

    print(f"\n📌 Scraping & Posting Complete: ✅ {all_success} jobs, ⚠️ {all_failed} failed.")