import subprocess, sys, logging, time

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", level=logging.INFO)
logger = logging.getLogger("runner")

def main():
    logger.info("🚀 Starting...")
    ub = subprocess.Popen([sys.executable, "userbot.py"], stdout=sys.stdout, stderr=sys.stderr)
    logger.info(f"🤖 Userbot PID: {ub.pid}")
    time.sleep(3)
    logger.info("🤖 Main bot...")
    try:
        from main_bot import main as bot_main
        bot_main()
    except KeyboardInterrupt:
        logger.info("⏹")
    finally:
        ub.terminate()

if __name__ == "__main__":
    main()