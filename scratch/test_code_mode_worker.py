import unittest
from jarvis_agent.code_mode.code_mode import execute_code_mode, resume_code_mode

class TestCodeModeWorker(unittest.TestCase):
    def test_simple_exec(self):
        source = """
        return "Hello from Code Mode!";
        """
        result = execute_code_mode(source, catalog=[], namespaces=[])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["value"], "Hello from Code Mode!")
        
    def test_wait_and_resume(self):
        source = """
        const val = await yield_control("pause");
        return "Resumed with: " + val;
        """
        result = execute_code_mode(source, catalog=[], namespaces=[])
        self.assertEqual(result["status"], "waiting")
        self.assertTrue(len(result["pendingRequests"]) == 1)
        
        req = result["pendingRequests"][0]
        self.assertEqual(req["method"], "yield")
        self.assertEqual(req["args"], ["pause"])
        
        # Resume with the settled request
        run_id = result["runId"]
        settled = [{
            "id": req["id"],
            "ok": True,
            "value": "resumed_value",
            "error": None
        }]
        
        resume_result = resume_code_mode(run_id, settled)
        self.assertEqual(resume_result["status"], "completed")
        self.assertEqual(resume_result["value"], "Resumed with: resumed_value")

if __name__ == '__main__':
    unittest.main()
