import os
import subprocess
import sys

root = r"c:\Users\PKFSCIT-RIAZ\projects\school_system"
os.chdir(root)
cmd = [
    sys.executable,
    "manage.py",
    "test",
    "students.tests.ExamWorkflowTests.test_exam_form_uses_dropdowns_for_class_and_section",
    "students.tests.ExamWorkflowTests.test_delete_exam_route_is_disabled_for_permanent_results",
    "-v",
    "2",
]
print("Running:", " ".join(cmd))
result = subprocess.run(cmd, text=True)
raise SystemExit(result.returncode)
