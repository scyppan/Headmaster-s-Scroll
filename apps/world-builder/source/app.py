if __name__ == "__main__":
    from launcher import run_application

    run_application()
else:
    from mage_maker.shell.application import MageMakerApp as App
