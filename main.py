import os
import re
import json
import time
import docx
import PyPDF2
import random
import sqlite3
import logging
import smtplib
import threading
import requests
import tkinter as tk

from transformers import pipeline
from user_agents import parse
from datetime import datetime
from urllib.parse import quote_plus, urljoin
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from email import encoders
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from tkinter import ttk, filedialog, messagebox, scrolledtext

def get_random_user_agent():
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15'
    ]
    return random.choice(user_agents)

class JobSearchApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Automated Job Search & Application System")
        self.root.geometry("1200x800")
        self.last_search_keywords = None
        self.last_search_location = None
        self.last_site_index = 0

        # Initialize Model
        self.summarizer = pipeline("summarization", model="facebook/bart-large-cnn")
        
        # Initialize database
        self.init_database()
        
        # CV content
        self.cv_content = ""
        self.cv_file_path = ""
        
        # Email settings
        self.email_settings = {
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': 587,
            'email': '',
            'password': '',
            'sender_name': ''
        }
        
        # Job search keywords (extracted from CV)
        self.search_keywords = []
        
        self.create_widgets()
        
    def init_database(self):
        """Initialize SQLite database"""
        self.conn = sqlite3.connect('job_applications.db')
        self.cursor = self.conn.cursor()
        
        # Create jobs table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                job_title TEXT NOT NULL,
                job_description TEXT,
                email TEXT,
                url TEXT,
                location TEXT,
                salary TEXT,
                date_found DATE,
                status TEXT DEFAULT 'Found',
                applied_date DATE,
                notes TEXT
            )
        ''')
        
        # Create email_queue table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER,
                recipient_email TEXT,
                subject TEXT,
                body TEXT,
                status TEXT DEFAULT 'Pending',
                created_date DATE,
                sent_date DATE,
                FOREIGN KEY (job_id) REFERENCES jobs (id)
            )
        ''')
        
        self.conn.commit()
        
    def create_widgets(self):
        """Create main GUI widgets"""
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Tab 1: CV Upload and Setup
        self.setup_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.setup_tab, text="Setup")
        self.create_setup_tab()
        
        # Tab 2: Job Search
        self.search_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.search_tab, text="Job Search")
        self.create_search_tab()
        
        # Tab 3: Job Database
        self.jobs_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.jobs_tab, text="Job Database")
        self.create_jobs_tab()
        
        # Tab 4: Email Configuration
        self.email_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.email_tab, text="Email Setup")
        self.create_email_tab()
        
        # Tab 5: Email Queue
        self.queue_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.queue_tab, text="Email Queue")
        self.create_queue_tab()
        
    def create_setup_tab(self):
        """Create setup tab widgets"""
        # CV Upload Section
        cv_frame = ttk.LabelFrame(self.setup_tab, text="CV Upload", padding="10")
        cv_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(cv_frame, text="Upload CV", command=self.upload_cv).pack(side='left', padx=5)
        self.cv_label = ttk.Label(cv_frame, text="No CV uploaded")
        self.cv_label.pack(side='left', padx=10)
        
        # CV Content Preview
        content_frame = ttk.LabelFrame(self.setup_tab, text="CV Content Preview", padding="10")
        content_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        self.cv_text = scrolledtext.ScrolledText(content_frame, height=15)
        self.cv_text.pack(fill='both', expand=True)
        
        # Extract Keywords Button
        ttk.Button(content_frame, text="Extract Keywords for Job Search", 
                  command=self.extract_keywords).pack(pady=5)
        
    def create_search_tab(self):
        """Create job search tab widgets"""
        # Search Parameters
        params_frame = ttk.LabelFrame(self.search_tab, text="Search Parameters", padding="10")
        params_frame.pack(fill='x', padx=10, pady=5)
        
        # Keywords
        ttk.Label(params_frame, text="Keywords:").grid(row=0, column=0, sticky='w', padx=5)
        self.keywords_entry = ttk.Entry(params_frame, width=50)
        self.keywords_entry.grid(row=0, column=1, padx=5, pady=2)
        
        # Location
        ttk.Label(params_frame, text="Location:").grid(row=1, column=0, sticky='w', padx=5)
        self.location_entry = ttk.Entry(params_frame, width=50)
        self.location_entry.grid(row=1, column=1, padx=5, pady=2)
        self.location_entry.insert(0, "Kenya")
        
        # Job Sites
        ttk.Label(params_frame, text="Job Sites:").grid(row=2, column=0, sticky='w', padx=5)
        sites_frame = ttk.Frame(params_frame)
        sites_frame.grid(row=2, column=1, sticky='w', padx=5, pady=2)
        
        self.site_vars = {}
        sites = ['Indeed', 'Glassdoor', 'CareerBuilder', 'Google Jobs', 'BrighterMonday', 'Remote OK', 'We Work Remotely']
        # Create checkboxes for each job site
        for i, site in enumerate(sites):
            var = tk.BooleanVar(value=True)
            self.site_vars[site] = var
            ttk.Checkbutton(sites_frame, text=site, variable=var).grid(row=0, column=i, padx=5)
        
        # Search Controls
        controls_frame = ttk.Frame(params_frame)
        controls_frame.grid(row=3, column=0, columnspan=2, pady=10)
        
        ttk.Button(controls_frame, text="Start Job Search", 
                  command=self.start_job_search).pack(side='left', padx=5)
        ttk.Button(controls_frame, text="Stop Search", 
                  command=self.stop_job_search).pack(side='left', padx=5)
        
        # Progress Bar
        self.progress = ttk.Progressbar(params_frame, mode='indeterminate')
        self.progress.grid(row=4, column=0, columnspan=2, sticky='ew', padx=5, pady=5)
        
        # Search Results
        results_frame = ttk.LabelFrame(self.search_tab, text="Search Results", padding="10")
        results_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        self.search_results = scrolledtext.ScrolledText(results_frame, height=15)
        self.search_results.pack(fill='both', expand=True)
        
    def create_jobs_tab(self):
        """Create jobs database tab widgets"""
        # Controls
        controls_frame = ttk.Frame(self.jobs_tab)
        controls_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(controls_frame, text="Refresh", command=self.refresh_jobs).pack(side='left', padx=5)
        ttk.Button(controls_frame, text="Delete Selected", command=self.delete_selected_job).pack(side='left', padx=5)
        ttk.Button(controls_frame, text="Generate Applications", command=self.generate_applications).pack(side='left', padx=5)
        
        # Jobs Treeview
        tree_frame = ttk.Frame(self.jobs_tab)
        tree_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Create treeview with scrollbars
        self.jobs_tree = ttk.Treeview(tree_frame, columns=('Company', 'Job Title', 'Location', 'Email', 'URL', 'Status'), show='headings')
        
        # Configure columns
        self.jobs_tree.heading('Company', text='Company')
        self.jobs_tree.heading('Job Title', text='Job Title')
        self.jobs_tree.heading('Location', text='Location')
        self.jobs_tree.heading('Email', text='Email')
        self.jobs_tree.heading('URL', text='URL')
        self.jobs_tree.heading('Status', text='Status')

        self.jobs_tree.column('Company', width=200)
        self.jobs_tree.column('Job Title', width=250)
        self.jobs_tree.column('Location', width=150)
        self.jobs_tree.column('Email', width=200)
        self.jobs_tree.column('URL', width=250)
        self.jobs_tree.column('Status', width=100)
        
        # Scrollbars
        v_scrollbar = ttk.Scrollbar(tree_frame, orient='vertical', command=self.jobs_tree.yview)
        h_scrollbar = ttk.Scrollbar(tree_frame, orient='horizontal', command=self.jobs_tree.xview)
        self.jobs_tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        # Pack treeview and scrollbars
        self.jobs_tree.pack(side='left', fill='both', expand=True)
        v_scrollbar.pack(side='right', fill='y')
        h_scrollbar.pack(side='bottom', fill='x')
        
        # Job details frame
        details_frame = ttk.LabelFrame(self.jobs_tab, text="Job Details", padding="10")
        details_frame.pack(fill='x', padx=10, pady=5)
        
        self.job_details = scrolledtext.ScrolledText(details_frame, height=8)
        self.job_details.pack(fill='both', expand=True)
        
        # Bind selection event
        self.jobs_tree.bind('<<TreeviewSelect>>', self.on_job_select)
        
    def create_email_tab(self):
        """Create email configuration tab widgets"""
        # Email Settings
        settings_frame = ttk.LabelFrame(self.email_tab, text="Email Settings", padding="10")
        settings_frame.pack(fill='x', padx=10, pady=5)
        
        # SMTP Settings
        ttk.Label(settings_frame, text="SMTP Server:").grid(row=0, column=0, sticky='w', padx=5)
        self.smtp_server_entry = ttk.Entry(settings_frame, width=30)
        self.smtp_server_entry.grid(row=0, column=1, padx=5, pady=2)
        self.smtp_server_entry.insert(0, "smtp.gmail.com")
        
        ttk.Label(settings_frame, text="SMTP Port:").grid(row=0, column=2, sticky='w', padx=5)
        self.smtp_port_entry = ttk.Entry(settings_frame, width=10)
        self.smtp_port_entry.grid(row=0, column=3, padx=5, pady=2)
        self.smtp_port_entry.insert(0, "587")
        
        ttk.Label(settings_frame, text="Email:").grid(row=1, column=0, sticky='w', padx=5)
        self.email_entry = ttk.Entry(settings_frame, width=30)
        self.email_entry.grid(row=1, column=1, padx=5, pady=2)
        
        ttk.Label(settings_frame, text="Password:").grid(row=1, column=2, sticky='w', padx=5)
        self.password_entry = ttk.Entry(settings_frame, width=20, show='*')
        self.password_entry.grid(row=1, column=3, padx=5, pady=2)
        
        ttk.Label(settings_frame, text="Sender Name:").grid(row=2, column=0, sticky='w', padx=5)
        self.sender_name_entry = ttk.Entry(settings_frame, width=30)
        self.sender_name_entry.grid(row=2, column=1, padx=5, pady=2)
        self.sender_name_entry.insert(0, "Peter Kangichu")
        
        ttk.Button(settings_frame, text="Test Connection", command=self.test_email_connection).grid(row=3, column=0, columnspan=2, pady=10)
        
        # Email Templates
        template_frame = ttk.LabelFrame(self.email_tab, text="Email Templates", padding="10")
        template_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Subject Template
        ttk.Label(template_frame, text="Subject Template:").pack(anchor='w', pady=2)
        self.subject_template = ttk.Entry(template_frame, width=80)
        self.subject_template.pack(fill='x', pady=2)
        self.subject_template.insert(0, "Application for {job_title} Position at {company_name}")
        
        # Body Template
        ttk.Label(template_frame, text="Email Body Template:").pack(anchor='w', pady=2)
        self.body_template = scrolledtext.ScrolledText(template_frame, height=15)
        self.body_template.pack(fill='both', expand=True, pady=2)
        
        default_template = """Dear Hiring Manager,

            I am writing to express my strong interest in the {job_title} position at {company_name}. With over 6 years of experience as a Full Stack Developer, I am confident that my technical expertise and proven track record make me an ideal candidate for this role.

            In my previous roles, I have:
            • Developed scalable web applications using PHP, Laravel, JavaScript, and Node.js
            • Led API development and third-party integrations
            • Implemented CI/CD pipelines and automated deployment processes
            • Worked with various database technologies including PostgreSQL and MySQL
            • Delivered high-performance solutions using Agile methodologies

            I am particularly excited about the opportunity to contribute to {company_name}'s continued success and would welcome the chance to discuss how my skills and experience align with your needs.

            Please find my resume attached for your review. I look forward to hearing from you soon.

            Best regards,
            Peter Kangichu
            +254759000845
            peternjeru6@live.com"""
        
        self.body_template.insert('1.0', default_template)
        
        # File attachments
        attachments_frame = ttk.LabelFrame(self.email_tab, text="Attachments", padding="10")
        attachments_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(attachments_frame, text="Select CV File", command=self.select_cv_attachment).pack(side='left', padx=5)
        self.cv_attachment_label = ttk.Label(attachments_frame, text="No CV selected")
        self.cv_attachment_label.pack(side='left', padx=10)
        
        ttk.Button(attachments_frame, text="Select Cover Letter", command=self.select_cover_letter).pack(side='left', padx=5)
        self.cover_letter_label = ttk.Label(attachments_frame, text="No cover letter selected")
        self.cover_letter_label.pack(side='left', padx=10)
        
    def create_queue_tab(self):
        """Create email queue tab widgets"""
        # Controls
        controls_frame = ttk.Frame(self.queue_tab)
        controls_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(controls_frame, text="Refresh Queue", command=self.refresh_email_queue).pack(side='left', padx=5)
        ttk.Button(controls_frame, text="Send Selected", command=self.send_selected_emails).pack(side='left', padx=5)
        ttk.Button(controls_frame, text="Send All", command=self.send_all_emails).pack(side='left', padx=5)
        ttk.Button(controls_frame, text="Delete Selected", command=self.delete_selected_email).pack(side='left', padx=5)
        
        # Email Queue Treeview
        queue_tree_frame = ttk.Frame(self.queue_tab)
        queue_tree_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        self.email_tree = ttk.Treeview(queue_tree_frame, columns=('Company', 'Job Title', 'Email', 'Status'), show='headings')
        
        # Configure columns
        self.email_tree.heading('Company', text='Company')
        self.email_tree.heading('Job Title', text='Job Title')
        self.email_tree.heading('Email', text='Email')
        self.email_tree.heading('Status', text='Status')
        
        self.email_tree.column('Company', width=200)
        self.email_tree.column('Job Title', width=250)
        self.email_tree.column('Email', width=200)
        self.email_tree.column('Status', width=100)
        
        # Scrollbars for email queue
        v_scrollbar2 = ttk.Scrollbar(queue_tree_frame, orient='vertical', command=self.email_tree.yview)
        h_scrollbar2 = ttk.Scrollbar(queue_tree_frame, orient='horizontal', command=self.email_tree.xview)
        self.email_tree.configure(yscrollcommand=v_scrollbar2.set, xscrollcommand=h_scrollbar2.set)
        
        # Pack treeview and scrollbars
        self.email_tree.pack(side='left', fill='both', expand=True)
        v_scrollbar2.pack(side='right', fill='y')
        h_scrollbar2.pack(side='bottom', fill='x')
        
        # Email Preview
        preview_frame = ttk.LabelFrame(self.queue_tab, text="Email Preview", padding="10")
        preview_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        self.email_preview = scrolledtext.ScrolledText(preview_frame, height=10)
        self.email_preview.pack(fill='both', expand=True)
        
        # Bind selection event
        self.email_tree.bind('<<TreeviewSelect>>', self.on_email_select)
        
    def upload_cv(self):
        """Upload and read CV file"""
        file_path = filedialog.askopenfilename(
            title="Select CV file",
            filetypes=[("PDF files", "*.pdf"), ("Word files", "*.docx"), ("Text files", "*.txt")]
        )
        
        if file_path:
            self.cv_file_path = file_path
            self.cv_content = self.read_cv_file(file_path)
            
            # Update UI
            self.cv_label.config(text=f"CV loaded: {os.path.basename(file_path)}")
            self.cv_text.delete('1.0', tk.END)
            self.cv_text.insert('1.0', self.cv_content)
            
    def read_cv_file(self, file_path):
        """Read content from CV file"""
        try:
            if file_path.endswith('.pdf'):
                return self.read_pdf(file_path)
            elif file_path.endswith('.docx'):
                return self.read_docx(file_path)
            elif file_path.endswith('.txt'):
                with open(file_path, 'r', encoding='utf-8') as file:
                    return file.read()
            else:
                return "Unsupported file format"
        except Exception as e:
            return f"Error reading file: {str(e)}"
    
    def read_pdf(self, file_path):
        """Read PDF file"""
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text()
                return text
        except Exception as e:
            return f"Error reading PDF: {str(e)}"
    
    def read_docx(self, file_path):
        """Read DOCX file"""
        try:
            doc = docx.Document(file_path)
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text
        except Exception as e:
            return f"Error reading DOCX: {str(e)}"
    
    def extract_keywords(self):
        """Extract keywords from CV for job search (improved)"""
        if not self.cv_content:
            messagebox.showwarning("Warning", "Please upload a CV first")
            return
    
        cv_text = self.cv_content.lower()
    
        # Define lists of skills, technologies, and job titles
        tech_skills = [
            'python', 'javascript', 'php', 'laravel', 'node.js', 'angular', 'react',
            'mysql', 'postgresql', 'mongodb', 'git', 'docker', 'aws', 'azure',
            'jenkins', 'ci/cd', 'rest api', 'graphql', 'full stack', 'backend',
            'frontend', 'web development', 'software development', 'database',
            'agile', 'scrum', 'devops', 'machine learning', 'ai', 'data science'
        ]
        job_titles = [
            'developer', 'engineer', 'software engineer', 'web developer', 'backend developer',
            'frontend developer', 'full stack developer', 'data scientist', 'devops engineer',
            'project manager', 'product manager', 'qa engineer', 'test engineer'
        ]
        soft_skills = [
            'leadership', 'communication', 'teamwork', 'problem solving', 'adaptability',
            'critical thinking', 'collaboration', 'creativity', 'time management'
        ]
    
        # Combine all keywords
        all_keywords = tech_skills + job_titles + soft_skills
    
        # Find all keywords in CV using regex for word boundaries
        found = []
        for kw in all_keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', cv_text):
                found.append(kw.title())
    
        # Remove duplicates and sort by frequency in CV
        found = list(dict.fromkeys(found))
        found_sorted = sorted(found, key=lambda x: cv_text.count(x.lower()), reverse=True)
    
        # Set keywords in search tab (top 10)
        keywords = ", ".join(found_sorted[:10])
        self.keywords_entry.delete(0, tk.END)
        self.keywords_entry.insert(0, keywords)
    
        messagebox.showinfo(
            "Keywords Extracted",
            f"Found {len(found_sorted)} relevant keywords. Top keywords set in search tab."
        )
    
    def start_job_search(self):
        """Start job search in a separate thread"""
        if not self.cv_content:
            messagebox.showwarning("Warning", "Please upload a CV first")
            return
    
        keywords = self.keywords_entry.get()
        location = self.location_entry.get()
    
        if not keywords:
            messagebox.showwarning("Warning", "Please enter search keywords")
            return
    
        # Check if keywords/location changed
        if keywords != self.last_search_keywords or location != self.last_search_location:
            self.last_site_index = 0  # Reset to first site
    
        self.last_search_keywords = keywords
        self.last_search_location = location
    
        self.stop_search_flag = False  # Reset stop flag before starting
        self.search_thread = threading.Thread(
            target=self.search_jobs, 
            args=(keywords, location, self.last_site_index)
        )
        self.search_thread.daemon = True
        self.search_thread.start()
        self.progress.start()
        
    def stop_job_search(self):
        """Stop job search"""
        self.stop_search_flag = True
        self.progress.stop()
        self.update_search_results("Stopping search...\n")
        
    def search_jobs(self, keywords, location, start_index=0):
        """Search for jobs on various platforms"""
        selected_sites = [site for site, var in self.site_vars.items() if var.get()]
        self.update_search_results(f"Starting job search for: {keywords} in {location}\n")
        self.update_search_results(f"Searching on: {', '.join(selected_sites)}\n\n")
        jobs_found = 0
        for idx, site in enumerate(selected_sites[start_index:], start=start_index):
            if self.stop_search_flag:
                self.update_search_results("Search stopped by user.\n")
                self.last_site_index = idx  # Save where we stopped
                break
            try:
                if site == 'Indeed':
                    jobs_found += self.search_indeed(keywords, location)
                elif site == 'Glassdoor':
                    jobs_found += self.search_glassdoor(keywords, location)
                elif site == 'CareerBuilder':
                    jobs_found += self.search_careerbuilder(keywords, location)
                elif site == 'Google Jobs':
                    jobs_found += self.search_google_jobs(keywords, location)
                elif site == 'BrighterMonday':
                    jobs_found += self.search_brightermonday(keywords, location)
                elif site == 'Remote OK':
                    jobs_found += self.search_remoteok(keywords)
                elif site == 'We Work Remotely':
                    jobs_found += self.search_weworkremotely(keywords)
            except Exception as e:
                self.update_search_results(f"Error searching {site}: {str(e)}\n")
            if self.stop_search_flag:
                self.update_search_results("Search stopped by user.\n")
                self.last_site_index = idx  # Save where we stopped
                break
        else:
            self.last_site_index = 0  # Reset if finished all sites
    
        self.update_search_results(f"\nSearch completed! Found {jobs_found} jobs total.\n")
        self.progress.stop()
        
    def get_edge_driver(self):
        edge_options = EdgeOptions()
        edge_options.add_argument('--headless')  #
        edge_options.add_argument('--disable-gpu')
        edge_options.add_argument('--no-sandbox')
        edge_options.add_argument('--disable-software-rasterizer')
        edge_options.add_argument(f'--user-agent={get_random_user_agent()}')
        driver_path = r"C:\WebDriver\msedgedriver.exe"
        driver = webdriver.Edge(service=EdgeService(driver_path), options=edge_options)
        return driver
    
    def search_indeed(self, keywords, location, max_pages=3):
        """Search Indeed for jobs using Selenium to bypass anti-bot measures."""
        try:
            self.update_search_results("Searching Indeed...\n")
            jobs_found = 0
            logger = logging.getLogger(__name__)
            
            # Configure headless Chrome
            driver = self.get_edge_driver()
            
            base_url = "https://www.indeed.com/jobs"
            params = {
                'q': keywords,
                'l': location,
                'fromage': '7'  # Last 7 days
            }
            
            for page in range(max_pages):
                params['start'] = page * 10
                url = f"{base_url}?q={quote_plus(keywords)}&l={quote_plus(location)}&fromage=7&start={page * 10}"
                driver.get(url)
                time.sleep(random.uniform(2, 4))  # Randomized delay
                soup = BeautifulSoup(driver.page_source, 'lxml')
                job_cards = soup.select('div.job_seen_beacon')
                
                if not job_cards:
                    logger.info(f"No more jobs found on Indeed page {page + 1}")
                    self.update_search_results(f"No more jobs found on Indeed page {page + 1}\n")
                    break
                    
                for job_card in job_cards:
                    try:
                        title = job_card.select_one('h2.jobTitle span')
                        company = job_card.select_one('span.companyName')
                        location_elem = job_card.select_one('div.companyLocation')
                        url_elem = job_card.select_one('a')
                        description_elem = job_card.select_one('div.job-snippet')
                        
                        job = {
                            'company': company.get_text(strip=True) if company else 'N/A',
                            'title': title.get_text(strip=True) if title else 'N/A',
                            'location': location_elem.get_text(strip=True) if location_elem else 'N/A',
                            'email': '',
                            'description': description_elem.get_text(strip=True) if description_elem else '',
                            'url': urljoin("https://www.indeed.com", url_elem['href']) if url_elem and url_elem.has_attr('href') else '',
                            'salary': ''
                        }
                        
                        if job['url']:
                            driver.get(job['url'])
                            time.sleep(random.uniform(1, 2))
                            try:
                                job_page = BeautifulSoup(driver.page_source, 'lxml')
                                description_elem = job_page.select_one('div#jobDescriptionText')
                                if description_elem:
                                    job['description'] = description_elem.get_text(strip=True)
                                salary_elem = job_page.select_one('div#salaryInfoAndJobType')
                                if salary_elem:
                                    job['salary'] = salary_elem.get_text(strip=True)
                                emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', job['description'])
                                if emails:
                                    job['email'] = emails[0]
                            except Exception as e:
                                logger.warning(f"Error fetching details for job {job['title']}: {str(e)}")
                        
                        self.save_job_to_db(job)
                        jobs_found += 1
                        self.update_search_results(f"Found: {job['title']} at {job['company']}\n")
                        time.sleep(random.uniform(0.5, 1))
                        
                    except Exception as e:
                        logger.error(f"Error processing Indeed job card: {str(e)}")
                        continue
                
                time.sleep(random.uniform(2, 4))
            
            driver.quit()
            logger.info(f"Indeed search completed. Found {jobs_found} jobs.")
            self.update_search_results(f"Indeed search completed. Found {jobs_found} jobs.\n")
            return jobs_found
            
        except Exception as e:
            logger.error(f"Error in Indeed search: {str(e)}")
            self.update_search_results(f"Error searching Indeed: {str(e)}\n")
            if 'driver' in locals():
                driver.quit()
            return 0
    
    def search_glassdoor(self, keywords, location, max_pages=3):
        """Search Glassdoor for jobs using Selenium to bypass anti-bot measures."""
        try:
            self.update_search_results("Searching Glassdoor...\n")
            jobs_found = 0
            logger = logging.getLogger(__name__)
            
            driver = self.get_edge_driver()

            base_url = "https://www.glassdoor.com/Job/jobs.htm"
            
            for page in range(max_pages):
                url = f"{base_url}?sc.keyword={quote_plus(keywords)}&locT=C&locKeyword={quote_plus(location)}&page={page + 1}"
                driver.get(url)
                time.sleep(random.uniform(2, 4))
                soup = BeautifulSoup(driver.page_source, 'lxml')
                job_cards = soup.select('li.react-job-listing')
                
                if not job_cards:
                    logger.info(f"No more jobs found on Glassdoor page {page + 1}")
                    self.update_search_results(f"No more jobs found on Glassdoor page {page + 1}\n")
                    break
                    
                for job_card in job_cards:
                    try:
                        title_elem = job_card.select_one('a.jobLink span')
                        company_elem = job_card.select_one('div.jobHeader a')
                        location_elem = job_card.select_one('span.pr-xxsm')
                        url_elem = job_card.select_one('a.jobLink')
                        
                        job = {
                            'company': company_elem.get_text(strip=True) if company_elem else 'N/A',
                            'title': title_elem.get_text(strip=True) if title_elem else 'N/A',
                            'location': location_elem.get_text(strip=True) if location_elem else 'N/A',
                            'email': '',
                            'description': '',
                            'url': urljoin("https://www.glassdoor.com", url_elem['href']) if url_elem and url_elem.has_attr('href') else '',
                            'salary': ''
                        }
                        
                        if job['url']:
                            driver.get(job['url'])
                            time.sleep(random.uniform(1, 2))
                            try:
                                job_page = BeautifulSoup(driver.page_source, 'lxml')
                                description_elem = job_page.select_one('div.desc')
                                if description_elem:
                                    job['description'] = description_elem.get_text(strip=True)
                                salary_elem = job_page.select_one('span.salary')
                                if salary_elem:
                                    job['salary'] = salary_elem.get_text(strip=True)
                                emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', job['description'])
                                if emails:
                                    job['email'] = emails[0]
                            except Exception as e:
                                logger.warning(f"Error fetching details for job {job['title']}: {str(e)}")
                        
                        self.save_job_to_db(job)
                        jobs_found += 1
                        self.update_search_results(f"Found: {job['title']} at {job['company']}\n")
                        time.sleep(random.uniform(0.5, 1))
                        
                    except Exception as e:
                        logger.error(f"Error processing Glassdoor job card: {str(e)}")
                        continue
                
                time.sleep(random.uniform(2, 4))
            
            driver.quit()
            logger.info(f"Glassdoor search completed. Found {jobs_found} jobs.")
            self.update_search_results(f"Glassdoor search completed. Found {jobs_found} jobs.\n")
            return jobs_found
            
        except Exception as e:
            logger.error(f"Error in Glassdoor search: {str(e)}")
            self.update_search_results(f"Error searching Glassdoor: {str(e)}\n")
            if 'driver' in locals():
                driver.quit()
            return 0

    def search_careerbuilder(self, keywords, location, max_pages=3):
        """Search CareerBuilder for jobs using Selenium to bypass anti-bot measures."""
        try:
            self.update_search_results("Searching CareerBuilder...\n")
            jobs_found = 0
            logger = logging.getLogger(__name__)
            
            driver = self.get_edge_driver()
            
            base_url = "https://www.careerbuilder.com/jobs"
            
            for page in range(max_pages):
                url = f"{base_url}?keywords={quote_plus(keywords)}&location={quote_plus(location)}&page={page + 1}"
                driver.get(url)
                time.sleep(random.uniform(2, 4))
                soup = BeautifulSoup(driver.page_source, 'lxml')
                job_cards = soup.select('div.data-results-content-parent div.data-results-content-block')
                
                if not job_cards:
                    logger.info(f"No more jobs found on CareerBuilder page {page + 1}")
                    self.update_search_results(f"No more jobs found on CareerBuilder page {page + 1}\n")
                    break
                    
                for job_card in job_cards:
                    try:
                        title_elem = job_card.select_one('h2 a')
                        company_elem = job_card.select_one('div.data-details span[data-company]')
                        location_elem = job_card.select_one('div.data-details span[data-location]')
                        url_elem = job_card.select_one('h2 a')
                        
                        job = {
                            'company': company_elem.get_text(strip=True) if company_elem else 'N/A',
                            'title': title_elem.get_text(strip=True) if title_elem else 'N/A',
                            'location': location_elem.get_text(strip=True) if location_elem else 'N/A',
                            'email': '',
                            'description': '',
                            'url': url_elem['href'] if url_elem and url_elem.has_attr('href') else '',
                            'salary': ''
                        }
                        
                        if job['url']:
                            driver.get(job['url'])
                            time.sleep(random.uniform(1, 2))
                            try:
                                job_page = BeautifulSoup(driver.page_source, 'lxml')
                                description_elem = job_page.select_one('div.job-description')
                                if description_elem:
                                    job['description'] = description_elem.get_text(strip=True)
                                salary_elem = job_page.select_one('div.salary')
                                if salary_elem:
                                    job['salary'] = salary_elem.get_text(strip=True)
                                emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', job['description'])
                                if emails:
                                    job['email'] = emails[0]
                            except Exception as e:
                                logger.warning(f"Error fetching details for job {job['title']}: {str(e)}")
                        
                        self.save_job_to_db(job)
                        jobs_found += 1
                        self.update_search_results(f"Found: {job['title']} at {job['company']}\n")
                        time.sleep(random.uniform(0.5, 1))
                        
                    except Exception as e:
                        logger.error(f"Error processing CareerBuilder job card: {str(e)}")
                        continue
                
                time.sleep(random.uniform(2, 4))
            
            driver.quit()
            logger.info(f"CareerBuilder search completed. Found {jobs_found} jobs.")
            self.update_search_results(f"CareerBuilder search completed. Found {jobs_found} jobs.\n")
            return jobs_found
            
        except Exception as e:
            logger.error(f"Error in CareerBuilder search: {str(e)}")
            self.update_search_results(f"Error searching CareerBuilder: {str(e)}\n")
            if 'driver' in locals():
                driver.quit()
            return 0

    def search_google_jobs(self, keywords, location, max_pages=3):
        """Search Google Jobs using Selenium to bypass anti-bot measures."""
        try:
            self.update_search_results("Searching Google Jobs...\n")
            jobs_found = 0
            logger = logging.getLogger(__name__)
            
            driver = self.get_edge_driver()
            
            query = f"{keywords} jobs in {location}"
            
            for page in range(max_pages):
                url = f"https://www.google.com/search?q={quote_plus(query)}&start={page * 10}"
                driver.get(url)
                time.sleep(random.uniform(3, 5))
                soup = BeautifulSoup(driver.page_source, 'lxml')
                job_cards = soup.select('div[jsname="QGGMK"]')
                
                if not job_cards:
                    logger.info(f"No more jobs found on Google Jobs page {page + 1}")
                    self.update_search_results(f"No more jobs found on Google Jobs page {page + 1}\n")
                    break
                    
                for job_card in job_cards:
                    try:
                        title_elem = job_card.select_one('div[role="heading"]')
                        company_elem = job_card.select_one('div[class*="vNEEBe"]')
                        location_elem = job_card.select_one('div[class*="Qk80Jf"]')
                        
                        job = {
                            'company': company_elem.get_text(strip=True) if company_elem else 'N/A',
                            'title': title_elem.get_text(strip=True) if title_elem else 'N/A',
                            'location': location_elem.get_text(strip=True) if location_elem else 'N/A',
                            'email': '',
                            'description': '',
                            'url': '',
                            'salary': ''
                        }
                        
                        try:
                            job_card_elem = driver.find_element(By.CSS_SELECTOR, 'div[jsname="QGGMK"]')
                            job_card_elem.click()
                            time.sleep(random.uniform(1, 2))
                            job_page = BeautifulSoup(driver.page_source, 'lxml')
                            description_elem = job_page.select_one('div[class*="nDgy9d"]')
                            if description_elem:
                                job['description'] = description_elem.get_text(strip=True)
                            salary_elem = job_page.select_one('div[class*="nDgy9d"] span[class*="salary"]')
                            if salary_elem:
                                job['salary'] = salary_elem.get_text(strip=True)
                            emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', job['description'])
                            if emails:
                                job['email'] = emails[0]
                            url_elem = job_page.select_one('a[class*="pMhGee"]')
                            if url_elem and url_elem.has_attr('href'):
                                job['url'] = url_elem['href']
                        except Exception as e:
                            logger.warning(f"Error fetching details for job {job['title']}: {str(e)}")
                        
                        self.save_job_to_db(job)
                        jobs_found += 1
                        self.update_search_results(f"Found: {job['title']} at {job['company']}\n")
                        time.sleep(random.uniform(0.5, 1))
                        
                    except Exception as e:
                        logger.error(f"Error processing Google Jobs card: {str(e)}")
                        continue
                
                time.sleep(random.uniform(3, 5))
            
            driver.quit()
            logger.info(f"Google Jobs search completed. Found {jobs_found} jobs.")
            self.update_search_results(f"Google Jobs search completed. Found {jobs_found} jobs.\n")
            return jobs_found
            
        except Exception as e:
            logger.error(f"Error in Google Jobs search: {str(e)}")
            self.update_search_results(f"Error searching Google Jobs: {str(e)}\n")
            if 'driver' in locals():
                driver.quit()
            return 0

    def search_remoteok(self, keywords, max_pages=3):
        """Search Remote OK for jobs using Selenium to bypass anti-bot measures."""
        try:
            self.update_search_results("Searching Remote OK...\n")
            jobs_found = 0
            logger = logging.getLogger(__name__)
            
            driver = self.get_edge_driver()
            
            base_url = f"https://remoteok.com/remote-{quote_plus(keywords)}-jobs"
            
            for page in range(max_pages):
                url = f"{base_url}?page={page + 1}"
                driver.get(url)
                time.sleep(random.uniform(2, 4))
                soup = BeautifulSoup(driver.page_source, 'lxml')
                job_cards = soup.select('tr.job')
                
                if not job_cards:
                    logger.info(f"No more jobs found on Remote OK page {page + 1}")
                    self.update_search_results(f"No more jobs found on Remote OK page {page + 1}\n")
                    break
                    
                for job_card in job_cards:
                    try:
                        title_elem = job_card.select_one('h2')
                        company_elem = job_card.select_one('td.company')
                        url_elem = job_card.select_one('a.preventLink')
                        
                        job = {
                            'company': company_elem.get_text(strip=True) if company_elem else 'N/A',
                            'title': title_elem.get_text(strip=True) if title_elem else 'N/A',
                            'location': 'Remote',
                            'email': '',
                            'description': '',
                            'url': urljoin("https://remoteok.com", url_elem['href']) if url_elem and url_elem.has_attr('href') else '',
                            'salary': ''
                        }
                        
                        if job['url']:
                            driver.get(job['url'])
                            time.sleep(random.uniform(1, 2))
                            try:
                                job_page = BeautifulSoup(driver.page_source, 'lxml')
                                description_elem = job_page.select_one('div.description')
                                if description_elem:
                                    job['description'] = description_elem.get_text(strip=True)
                                salary_elem = job_page.select_one('span.salary')
                                if salary_elem:
                                    job['salary'] = salary_elem.get_text(strip=True)
                                emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', job['description'])
                                if emails:
                                    job['email'] = emails[0]
                            except Exception as e:
                                logger.warning(f"Error fetching details for job {job['title']}: {str(e)}")
                        
                        self.save_job_to_db(job)
                        jobs_found += 1
                        self.update_search_results(f"Found: {job['title']} at {job['company']}\n")
                        time.sleep(random.uniform(0.5, 1))
                        
                    except Exception as e:
                        logger.error(f"Error processing Remote OK job card: {str(e)}")
                        continue
                
                time.sleep(random.uniform(2, 4))
            
            driver.quit()
            logger.info(f"Remote OK search completed. Found {jobs_found} jobs.")
            self.update_search_results(f"Remote OK search completed. Found {jobs_found} jobs.\n")
            return jobs_found
            
        except Exception as e:
            logger.error(f"Error in Remote OK search: {str(e)}")
            self.update_search_results(f"Error searching Remote OK: {str(e)}\n")
            if 'driver' in locals():
                driver.quit()
            return 0

    def search_weworkremotely(self, keywords, max_pages=3):
        """Search We Work Remotely for jobs using Selenium to bypass anti-bot measures."""
        try:
            self.update_search_results("Searching We Work Remotely...\n")
            jobs_found = 0
            logger = logging.getLogger(__name__)
            
            driver = self.get_edge_driver()
            base_url = f"https://weworkremotely.com/remote-jobs/search?term={quote_plus(keywords)}"
            
            for page in range(max_pages):
                url = f"{base_url}&page={page + 1}"
                driver.get(url)
                time.sleep(random.uniform(2, 4))
                soup = BeautifulSoup(driver.page_source, 'lxml')
                job_cards = soup.select('section.jobs article')
                
                if not job_cards:
                    logger.info(f"No more jobs found on We Work Remotely page {page + 1}")
                    self.update_search_results(f"No more jobs found on We Work Remotely page {page + 1}\n")
                    break
                    
                for job_card in job_cards:
                    try:
                        title_elem = job_card.select_one('span.title')
                        company_elem = job_card.select_one('span.company')
                        url_elem = job_card.select_one('a')
                        
                        job = {
                            'company': company_elem.get_text(strip=True) if company_elem else 'N/A',
                            'title': title_elem.get_text(strip=True) if title_elem else 'N/A',
                            'location': 'Remote',
                            'email': '',
                            'description': '',
                            'url': urljoin("https://weworkremotely.com", url_elem['href']) if url_elem and url_elem.has_attr('href') else '',
                            'salary': ''
                        }
                        
                        if job['url']:
                            driver.get(job['url'])
                            time.sleep(random.uniform(1, 2))
                            try:
                                job_page = BeautifulSoup(driver.page_source, 'lxml')
                                description_elem = job_page.select_one('div.listing-container')
                                if description_elem:
                                    job['description'] = description_elem.get_text(strip=True)
                                salary_elem = job_page.select_one('div.salary')
                                if salary_elem:
                                    job['salary'] = salary_elem.get_text(strip=True)
                                emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', job['description'])
                                if emails:
                                    job['email'] = emails[0]
                            except Exception as e:
                                logger.warning(f"Error fetching details for job {job['title']}: {str(e)}")
                        
                        self.save_job_to_db(job)
                        jobs_found += 1
                        self.update_search_results(f"Found: {job['title']} at {job['company']}\n")
                        time.sleep(random.uniform(0.5, 1))
                        
                    except Exception as e:
                        logger.error(f"Error processing We Work Remotely job card: {str(e)}")
                        continue
                
                time.sleep(random.uniform(2, 4))
            
            driver.quit()
            logger.info(f"We Work Remotely search completed. Found {jobs_found} jobs.")
            self.update_search_results(f"We Work Remotely search completed. Found {jobs_found} jobs.\n")
            return jobs_found
            
        except Exception as e:
            logger.error(f"Error in We Work Remotely search: {str(e)}")
            self.update_search_results(f"Error searching We Work Remotely: {str(e)}\n")
            if 'driver' in locals():
                driver.quit()
            return 0
    
    def search_brightermonday(self, keywords, location, max_pages=3):
        """Search BrighterMonday for jobs using Selenium to bypass anti-bot measures."""
        try:
            self.update_search_results("Searching BrighterMonday...\n")
            jobs_found = 0
            logger = logging.getLogger(__name__)
            
            driver = self.get_edge_driver()
            
            base_url = "https://www.brightermonday.co.ke/jobs"
            
            for page in range(max_pages):
                url = f"{base_url}?search={quote_plus(keywords)}&location={quote_plus(location)}&page={page + 1}"
                driver.get(url)
                time.sleep(random.uniform(2, 4))
                soup = BeautifulSoup(driver.page_source, 'lxml')
                job_cards = soup.select('div.search-result')
                
                if not job_cards:
                    logger.info(f"No more jobs found on BrighterMonday page {page + 1}")
                    self.update_search_results(f"No more jobs found on BrighterMonday page {page + 1}\n")
                    break
                    
                for job_card in job_cards:
                    try:
                        title_elem = job_card.select_one('h3')
                        company_elem = job_card.select_one('a.company-name')
                        location_elem = job_card.select_one('span.location')
                        url_elem = job_card.select_one('a')
                        description_elem = job_card.select_one('div.job-desc')
                        
                        job = {
                            'company': company_elem.get_text(strip=True) if company_elem else 'N/A',
                            'title': title_elem.get_text(strip=True) if title_elem else 'N/A',
                            'location': location_elem.get_text(strip=True) if location_elem else 'N/A',
                            'email': '',
                            'description': description_elem.get_text(strip=True) if description_elem else '',
                            'url': urljoin("https://www.brightermonday.co.ke", url_elem['href']) if url_elem and url_elem.has_attr('href') else '',
                            'salary': ''
                        }
                        
                        if job['url']:
                            driver.get(job['url'])
                            time.sleep(random.uniform(1, 2))
                            try:
                                job_page = BeautifulSoup(driver.page_source, 'lxml')
                                description_elem = job_page.select_one('div.job-description')
                                if description_elem:
                                    job['description'] = description_elem.get_text(strip=True)
                                salary_elem = job_page.select_one('span.salary')
                                if salary_elem:
                                    job['salary'] = salary_elem.get_text(strip=True)
                                emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', job['description'])
                                if emails:
                                    job['email'] = emails[0]
                            except Exception as e:
                                logger.warning(f"Error fetching details for job {job['title']}: {str(e)}")
                        
                        self.save_job_to_db(job)
                        jobs_found += 1
                        self.update_search_results(f"Found: {job['title']} at {job['company']}\n")
                        time.sleep(random.uniform(0.5, 1))
                        
                    except Exception as e:
                        logger.error(f"Error processing BrighterMonday job card: {str(e)}")
                        continue
                
                time.sleep(random.uniform(2, 4))
            
            driver.quit()
            logger.info(f"BrighterMonday search completed. Found {jobs_found} jobs.")
            self.update_search_results(f"BrighterMonday search completed. Found {jobs_found} jobs.\n")
            return jobs_found
            
        except Exception as e:
            logger.error(f"Error in BrighterMonday search: {str(e)}")
            self.update_search_results(f"Error searching BrighterMonday: {str(e)}\n")
            if 'driver' in locals():
                driver.quit()
            return 0
    
    def save_job_to_db(self, job):
        """Save job to database (thread-safe)"""
        try:
            # Create a new connection for this thread
            conn = sqlite3.connect('job_applications.db')
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO jobs (company_name, job_title, job_description, email, url, location, date_found)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                job['company'],
                job['title'],
                job['description'],
                job['email'],
                job['url'],
                job['location'],
                datetime.now().strftime('%Y-%m-%d')
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error saving job to database: {str(e)}")
    
    def update_search_results(self, message):
        """Update search results text box"""
        self.root.after(0, lambda: self.search_results.insert(tk.END, message))
        self.root.after(0, lambda: self.search_results.see(tk.END))
    
    def refresh_jobs(self):
        """Refresh jobs in the treeview"""
        # Clear existing items
        for item in self.jobs_tree.get_children():
            self.jobs_tree.delete(item)
        
        # Fetch jobs from database
        self.cursor.execute('SELECT id, company_name, job_title, location, email, url, status FROM jobs ORDER BY date_found DESC')
        jobs = self.cursor.fetchall()

        for job in jobs:
            self.jobs_tree.insert('', 'end', values=(job[1], job[2], job[3], job[4], job[5], job[6]), tags=(job[0],))
        
    def on_job_select(self, event):
        """Handle job selection"""
        selection = self.jobs_tree.selection()
        if selection:
            item = self.jobs_tree.item(selection[0])
            job_id = item['tags'][0]
            
            # Fetch full job details
            self.cursor.execute('SELECT * FROM jobs WHERE id = ?', (job_id,))
            job = self.cursor.fetchone()
            
            if job:
                details = f"Company: {job[1]}\n"
                details += f"Job Title: {job[2]}\n"
                details += f"Location: {job[6]}\n"
                details += f"Email: {job[4]}\n"
                details += f"URL: {job[5]}\n"
                details += f"Date Found: {job[8]}\n"
                details += f"Status: {job[9]}\n\n"
                details += f"Description:\n{job[3]}\n"

                self.job_details.delete('1.0', tk.END)
                self.job_details.insert('1.0', details)
    
    def delete_selected_job(self):
        """Delete selected job"""
        selection = self.jobs_tree.selection()
        if selection:
            item = self.jobs_tree.item(selection[0])
            job_id = item['tags'][0]
            
            if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this job?"):
                self.cursor.execute('DELETE FROM jobs WHERE id = ?', (job_id,))
                self.conn.commit()
                self.refresh_jobs()
    
    def summarize_experience(self, experience_text):
        """
        Summarize the relevant experience using a free language model.
        """
        # Hugging Face models have input length limits (1024 tokens for BART)
        if not experience_text.strip():
            return ""
        try:
            summary = self.summarizer(experience_text[:1024], max_length=80, min_length=30, do_sample=False)[0]['summary_text']
            return summary
        except Exception as e:
            return experience_text[:300]  # fallback: first 300 chars
    
    def get_relevant_experience(self, job_title, keywords):
        """
        Extract and return relevant experience lines from CV that match the job title or keywords.
        """
        experience_text = self.extract_experience(self.cv_content)
        if not experience_text:
            return ""
        # Split experience into lines
        lines = experience_text.split('\n')
        relevant_lines = []
        # Combine job title and keywords for matching
        match_terms = [job_title.lower()] + [kw.strip().lower() for kw in keywords.split(',')]
        for line in lines:
            if any(term in line.lower() for term in match_terms):
                relevant_lines.append(line.strip())
        # If nothing matched, fallback to first 3 lines
        if not relevant_lines:
            relevant_lines = lines[:3]
        return "\n".join(relevant_lines)
    
    def generate_applications(self):
        """Generate email applications for all jobs"""
        self.cursor.execute('SELECT * FROM jobs WHERE status = "Found"')
        jobs = self.cursor.fetchall()
        
        if not jobs:
            messagebox.showinfo("No Jobs", "No jobs found to generate applications for.")
            return
        
        subject_template = self.subject_template.get()
        body_template = self.body_template.get('1.0', tk.END)
        
        generated_count = 0
        
        for job in jobs:
            job_id, company_name, job_title, description, email, url, location, salary, date_found, status, applied_date, notes = job
            
            if not email:
                continue
            
            subject = subject_template.format(
                job_title=job_title,
                company_name=company_name,
                location=location
            )
            
            # Get relevant experience for this job
            relevant_experience = self.get_relevant_experience(job_title, self.keywords_entry.get())
            summarized_exp = self.summarize_experience(relevant_experience)
            if summarized_exp:
                experience_block = f"\nRelevant Experience:\n{summarized_exp}\n"
            else:
                experience_block = ""
            
            body = body_template.format(
                job_title=job_title,
                company_name=company_name,
                location=location,
                experience=experience_block
            )
            # body += experience_block
            
            self.cursor.execute('''
                INSERT INTO email_queue (job_id, recipient_email, subject, body, created_date)
                VALUES (?, ?, ?, ?, ?)
            ''', (job_id, email, subject, body, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            
            generated_count += 1
        
        self.conn.commit()
        messagebox.showinfo("Applications Generated", f"Generated {generated_count} email applications.")
        self.refresh_email_queue()
    
    def test_email_connection(self):
        """Test email connection"""
        smtp_server = self.smtp_server_entry.get()
        smtp_port = int(self.smtp_port_entry.get())
        email = self.email_entry.get()
        password = self.password_entry.get()
        
        if not all([smtp_server, smtp_port, email, password]):
            messagebox.showwarning("Warning", "Please fill in all email settings")
            return
        
        try:
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(email, password)
            server.quit()
            messagebox.showinfo("Success", "Email connection test successful!")
        except Exception as e:
            messagebox.showerror("Error", f"Email connection failed: {str(e)}")
    
    def select_cv_attachment(self):
        """Select CV file for attachment"""
        file_path = filedialog.askopenfilename(
            title="Select CV file",
            filetypes=[("PDF files", "*.pdf"), ("Word files", "*.docx")]
        )
        
        if file_path:
            self.cv_attachment_path = file_path
            self.cv_attachment_label.config(text=f"CV: {os.path.basename(file_path)}")
    
    def select_cover_letter(self):
        """Select cover letter file for attachment"""
        file_path = filedialog.askopenfilename(
            title="Select cover letter file",
            filetypes=[("PDF files", "*.pdf"), ("Word files", "*.docx")]
        )
        
        if file_path:
            self.cover_letter_path = file_path
            self.cover_letter_label.config(text=f"Cover Letter: {os.path.basename(file_path)}")
    
    def refresh_email_queue(self):
        """Refresh email queue"""
        # Clear existing items
        for item in self.email_tree.get_children():
            self.email_tree.delete(item)
        
        # Fetch emails from database
        self.cursor.execute('''
            SELECT eq.id, j.company_name, j.job_title, eq.recipient_email, eq.status
            FROM email_queue eq
            JOIN jobs j ON eq.job_id = j.id
            ORDER BY eq.created_date DESC
        ''')
        emails = self.cursor.fetchall()
        
        for email in emails:
            self.email_tree.insert('', 'end', values=(email[1], email[2], email[3], email[4]), tags=(email[0],))
    
    def on_email_select(self, event):
        """Handle email selection"""
        selection = self.email_tree.selection()
        if selection:
            item = self.email_tree.item(selection[0])
            email_id = item['tags'][0]
            
            # Fetch full email details
            self.cursor.execute('''
                SELECT eq.*, j.company_name, j.job_title
                FROM email_queue eq
                JOIN jobs j ON eq.job_id = j.id
                WHERE eq.id = ?
            ''', (email_id,))
            email = self.cursor.fetchone()
            
            if email:
                preview = f"To: {email[2]}\n"
                preview += f"Subject: {email[3]}\n\n"
                preview += f"{email[4]}\n"
                
                self.email_preview.delete('1.0', tk.END)
                self.email_preview.insert('1.0', preview)
    
    def send_selected_emails(self):
        """Send selected emails"""
        selection = self.email_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select emails to send")
            return
        
        email_ids = [self.email_tree.item(item)['tags'][0] for item in selection]
        self.send_emails(email_ids)
    
    def send_all_emails(self):
        """Send all pending emails"""
        self.cursor.execute('SELECT id FROM email_queue WHERE status = "Pending"')
        email_ids = [row[0] for row in self.cursor.fetchall()]
        
        if not email_ids:
            messagebox.showinfo("No Emails", "No pending emails to send.")
            return
        
        self.send_emails(email_ids)
    
    def send_emails(self, email_ids):
        """Send emails by IDs"""
        # Get email settings
        smtp_server = self.smtp_server_entry.get()
        smtp_port = int(self.smtp_port_entry.get())
        sender_email = self.email_entry.get()
        password = self.password_entry.get()
        sender_name = self.sender_name_entry.get()
        
        if not all([smtp_server, smtp_port, sender_email, password]):
            messagebox.showwarning("Warning", "Please configure email settings first")
            return
        
        # Check for attachments
        cv_attachment = getattr(self, 'cv_attachment_path', None)
        cover_letter = getattr(self, 'cover_letter_path', None)
        
        if not cv_attachment:
            messagebox.showwarning("Warning", "Please select a CV file for attachment")
            return
        
        sent_count = 0
        failed_count = 0
        
        try:
            # Connect to SMTP server
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(sender_email, password)
            
            for email_id in email_ids:
                try:
                    # Fetch email details
                    self.cursor.execute('SELECT * FROM email_queue WHERE id = ?', (email_id,))
                    email_data = self.cursor.fetchone()
                    
                    if not email_data:
                        continue
                    
                    _, job_id, recipient_email, subject, body, status, created_date, sent_date = email_data
                    
                    # Create email message
                    msg = MIMEMultipart()
                    msg['From'] = f"{sender_name} <{sender_email}>"
                    msg['To'] = recipient_email
                    msg['Subject'] = subject
                    
                    # Add body
                    msg.attach(MIMEText(body, 'plain'))
                    
                    # Add CV attachment
                    if cv_attachment:
                        with open(cv_attachment, 'rb') as attachment:
                            part = MIMEBase('application', 'octet-stream')
                            part.set_payload(attachment.read())
                            encoders.encode_base64(part)
                            part.add_header(
                                'Content-Disposition',
                                f'attachment; filename= {os.path.basename(cv_attachment)}'
                            )
                            msg.attach(part)
                    
                    # Add cover letter attachment
                    if cover_letter:
                        with open(cover_letter, 'rb') as attachment:
                            part = MIMEBase('application', 'octet-stream')
                            part.set_payload(attachment.read())
                            encoders.encode_base64(part)
                            part.add_header(
                                'Content-Disposition',
                                f'attachment; filename= {os.path.basename(cover_letter)}'
                            )
                            msg.attach(part)
                    
                    # Send email
                    server.send_message(msg)
                    
                    # Update email status
                    self.cursor.execute('''
                        UPDATE email_queue 
                        SET status = "Sent", sent_date = ?
                        WHERE id = ?
                    ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), email_id))
                    
                    # Update job status
                    self.cursor.execute('''
                        UPDATE jobs 
                        SET status = "Applied", applied_date = ?
                        WHERE id = ?
                    ''', (datetime.now().strftime('%Y-%m-%d'), job_id))
                    
                    sent_count += 1
                    
                    # Small delay to avoid overwhelming servers
                    time.sleep(1)
                    
                except Exception as e:
                    print(f"Error sending email {email_id}: {str(e)}")
                    failed_count += 1
                    
                    # Update email status to failed
                    self.cursor.execute('''
                        UPDATE email_queue 
                        SET status = "Failed"
                        WHERE id = ?
                    ''', (email_id,))
            
            server.quit()
            self.conn.commit()
            
            messagebox.showinfo("Email Sending Complete", 
                              f"Sent: {sent_count} emails\nFailed: {failed_count} emails")
            
            # Refresh displays
            self.refresh_email_queue()
            self.refresh_jobs()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to send emails: {str(e)}")
    
    def delete_selected_email(self):
        """Delete selected email from queue"""
        selection = self.email_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select emails to delete")
            return
        
        if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete selected emails?"):
            email_ids = [self.email_tree.item(item)['tags'][0] for item in selection]
            
            for email_id in email_ids:
                self.cursor.execute('DELETE FROM email_queue WHERE id = ?', (email_id,))
            
            self.conn.commit()
            self.refresh_email_queue()
    
    def __del__(self):
        """Cleanup database connection"""
        if hasattr(self, 'conn'):
            self.conn.close()


def main():
    """Main function to run the application"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()]
    )

    logging.info("Starting Automated Job Search & Application System...")
    root = tk.Tk()
    app = JobSearchApp(root)

    # Load initial data
    app.refresh_jobs()
    app.refresh_email_queue()

    try:
        root.mainloop()
    except KeyboardInterrupt:
        logging.info("Application interrupted by user (Ctrl+C). Closing...")
        if hasattr(app, 'conn'):
            app.conn.close()
        root.destroy()
    finally:
        logging.info("Application closed.")

if __name__ == "__main__":
    main()