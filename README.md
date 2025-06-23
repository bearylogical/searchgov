# SGDI Analytics

This project provides a platform for analyzing the Singapore Government Directory (SGDI) data. It constructs a temporal graph of organizations and personnel, allowing for insights into career progressions, organizational structures, and connectivity within the Singapore public service.

## Features

-   **Temporal Graph Database**: Models the evolution of government organizations and employment history over time using PostgreSQL with the AGE extension.
-   **Career Progression Analysis**: Trace the career path of individuals across different government bodies.
-   **Organizational Structure Visualization**: Generate and visualize organizational charts for ministries and their sub-entities at different points in time.
-   **Connectivity Analysis**: Find the shortest path of connections between any two individuals in the directory.
-   **Web Interface**: An interactive web application built with [NiceGUI](https://nicegui.io/) to explore the data and visualizations.
-   **Data Cleaning & Preprocessing**: Robust scripts to clean, process, and structure the raw SGDI data.

## Tech Stack

-   **Backend**: Python
-   **Web Framework**: [NiceGUI](https://nicegui.io/)
-   **Database**: PostgreSQL with [Apache AGE](https://age.apache.org/) extension for graph capabilities.
-   **Package Management**: [uv](https://github.com/astral-sh/uv)
-   **Containerization**: Docker, Docker Compose

## Setup and Installation

### Prerequisites

-   Python 3.12+
-   Docker and Docker Compose
-   [uv](https://github.com/astral-sh/uv) installed (`pip install uv`)

### 1. Database Setup

The application requires a PostgreSQL instance with the Apache AGE extension enabled. The easiest way to get this running is via Docker.

```bash
# You can use a pre-built image with AGE
docker run -p 5432:5432 -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=searchgov --name age_db -d apache/age
```

### 2. Environment Variables

Copy the sample environment file and update it with your database credentials if they differ from the defaults.

```bash
cp .env.sample .env
```

### 3. Install Dependencies

Use `uv` to sync the project dependencies from the lockfile.

```bash
uv sync --locked
```

### 4. Data Ingestion

The notebooks in the `notebooks/` directory are used for data processing and ingestion. You will need to run them in sequence to populate the database.

1.  **`notebooks/cleaning.ipynb`**: Cleans the raw data and produces `tenure.parquet` and `orgs.parquet`.
2.  **`notebooks/graph_ingestion.ipynb`**: Ingests the cleaned data into the PostgreSQL/AGE database.

## Running the Application

### Locally

Once the setup is complete, you can run the web application using `uv`.

```bash
uv run main.py
```

The application will be available at `http://localhost:8080`.

### Using Docker

You can also build and run the entire application using Docker Compose. This is the recommended method for deployment.

```bash
docker-compose up --build
```

The application will be available at `http://localhost:8080`.

## Project Structure

```
.
├── data/                # Raw and processed data (gitignored)
├── notebooks/           # Jupyter notebooks for data exploration, cleaning, and ingestion
├── src/                 # Main source code
│   ├── app/             # Core application logic (e.g., TemporalGraph)
│   ├── database/        # Database connection and schema management
│   ├── frontend/        # NiceGUI web interface components and views
│   ├── models/          # Machine learning models (e.g., name embeddings)
│   └── preprocess/      # Data preprocessing scripts
├── tests/               # Unit and integration tests
├── .env.sample          # Environment variable template
├── docker-compose.yml   # Docker Compose configuration
├── dockerfile           # Dockerfile for the application
├── main.py              # Main entry point for the NiceGUI app
└── pyproject.toml       # Project metadata and dependencies
```
