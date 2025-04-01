# AI-Powered Customer Complaint Handling System

## Overview
This project automates the process of handling customer complaints using **CrewAI**. It extracts key details from customer messages, classifies them, verifies policies, and generates appropriate responses. The system supports both **text and audio** inputs and is useful for industries like **e-commerce, service providers, and logistics**.

## Features
- **Automatic Complaint Analysis**: Extracts name, order ID, issue, and refund request.
- **Intelligent Classification**: Categorizes complaints into relevant types.
- **Policy Checking**: Ensures compliance with refund and escalation policies.
- **Response Generation**: Creates polite, structured responses based on the issue.
- **JSON Formatting**: Converts responses into structured JSON format.
- **Multi-Modal Input Support**: Processes both **text** and **audio complaints**.
- **CRM Integration**: Saves complaint details in a database using XAMPP.

## Technologies Used
- **Python 3.10+**
- **CrewAI** (AI agent orchestration)
- **Loguru** (for logging)
- **OpenAI API** (for natural language processing)
- **MySQL (via XAMPP)** (for storing customer complaints)

## Installation
### 1. Clone the Repository
```bash
  git clone https://github.com/Rohitkumarsony/crewai_mail_agent.git
  cd AI-Complaint-Handling
```

### 2. Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
venv\Scripts\activate    # On Windows
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Install Required Packages
Make sure the following dependencies are installed:
```bash
pip install crewai loguru openai mysql-connector-python
```

## Project Structure
```
AI-Complaint-Handling/
│── src/            
│   │── email_agent/
│   │   │── get_mail.py        # Email processing module
│   │   │── send_mail.py       # Sending response emails
│   │   │── crm.py             # CRM integration module (saves data)
│── requirements.txt           # Dependencies
│── README.md                  # Documentation
```

## Running the Project
Navigate to the `src` directory and execute the email processing module:
```bash
cd src
python3 -m email_agent.get_mail
```

## How It Works
1. **Customer sends a complaint (text/audio).**
2. **Complaint Analyzer extracts details** (customer name, issue, order ID, refund request, etc.).
3. **Complaint details are saved in the CRM database.**
4. **Response Generator crafts a polite response.**
5. **JSON Formatter formats the response into structured JSON.**
6. **The system sends the response automatically.**

## Example Output
```json
{
  "subject": "Assistance with Your Delivery Issue - Order TSR 5 TR vjg yd 123 U",
  "body": "Dear Ram,\n\nThank you for reaching out regarding your order (TSR 5 TR vjg yd 123 U). We understand your concern and are here to assist you. Please provide your address details so we can investigate further.\n\nBest regards,\nsupports@.com\nCustomer Service Team 24*7\n"
}
```

## Contributing
1. Fork the repo.
2. Create a new branch (`feature-name`).
3. Commit changes and push to GitHub.
4. Create a pull request.

## License
MIT License. See `LICENSE` for details.

