touch root_path.txt
rm root_path.txt
mkdir -p logs
uvicorn main_beanie:app --reload --reload-delay=4.0