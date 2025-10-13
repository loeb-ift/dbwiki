import os
import sys
import logging

# Configure logging to see detailed output
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('test_initial_prompt')

# Add the project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.append(project_root)

if __name__ == "__main__":
    try:
        logger.info("=== Testing MyVanna with initial_prompt parameter ===")
        
        # Import after path configuration
        from app.vanna_wrapper import get_vanna_instance
        
        # Set environment variables if needed
        os.environ['OLLAMA_MODEL'] = os.getenv('OLLAMA_MODEL', 'llama3')
        os.environ['OLLAMA_HOST'] = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
        
        # Get a Vanna instance
        logger.info("Creating Vanna instance...")
        vn = get_vanna_instance(user_id="test_user")
        logger.info("Successfully created Vanna instance")
        
        # This is the critical test - passing initial_prompt which was causing the TypeError
        logger.info("Testing generate_sql with initial_prompt parameter...")
        result = vn.generate_sql(
            question="What is the total sales?",
            initial_prompt="You are a SQL expert."
        )
        
        logger.info("✅ SUCCESS! The initial_prompt parameter was accepted without errors.")
        logger.info(f"Result type: {type(result)}")
        
        # Try with additional parameters like stream
        logger.info("Testing with stream=True...")
        result_stream = vn.generate_sql(
            question="What products are most popular?",
            initial_prompt="You are a SQL expert.",
            stream=True
        )
        logger.info("✅ SUCCESS! Stream parameter also works with initial_prompt.")
        
        logger.info("=== Test completed successfully ===")
        
    except Exception as e:
        logger.error(f"❌ Test failed with error: {type(e).__name__}: {e}")
        import traceback
        logger.error(f"Stack trace: {traceback.format_exc()}")
        sys.exit(1)