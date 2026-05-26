import re

def parse_task_file(content: str) -> dict:
    lines = content.splitlines()
    
    # Parse header metadata
    task_id = "000"
    title = "Unknown"
    if lines:
        task_id_match = re.search(r'# Task:\s*(\d+)\s*-\s*(.*)', lines[0])
        if task_id_match:
            task_id = task_id_match.group(1)
            title = task_id_match.group(2).strip()
            
    status = "PENDING"
    assigned_to = "LOCAL_AGENT_CODING"
    target_files = []
    
    for line in lines:
        if line.startswith("Status:"):
            status = line.split(":", 1)[1].strip()
        elif line.startswith("Assigned To:"):
            assigned_to = line.split(":", 1)[1].strip()
        elif line.strip().startswith("- `"):
            file_match = re.search(r'- `(.*?)`', line)
            if file_match:
                target_files.append(file_match.group(1))
                
    # Extract sections by heading markers
    # Split by the header format like "## [1. ORCHESTRATOR INSTRUCTIONS]"
    sections = re.split(r'## \[\d+\.\s+.*?\]', content)
    instructions = sections[1].strip() if len(sections) > 1 else ""
    context_files = sections[2].strip() if len(sections) > 2 else ""
    work_area = sections[3].strip() if len(sections) > 3 else ""
    execution_results = sections[4].strip() if len(sections) > 4 else ""
    
    return {
        "task_id": task_id,
        "title": title,
        "status": status,
        "assigned_to": assigned_to,
        "target_files": target_files,
        "instructions": instructions,
        "context_files": context_files,
        "work_area": work_area,
        "execution_results": execution_results
    }
