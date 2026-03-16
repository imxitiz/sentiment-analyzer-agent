from camoufox.sync_api import Camoufox

with Camoufox() as browser:
    page = browser.new_page()
    page.goto("https://www.bbc.com/news/articles/cev7z9802zjo")
    title = page.title()
    print(f"Page title: {title}")

    # # wait for the search box to be available, then type a query and submit it
    # page.wait_for_selector("textarea[title='Search'], textarea[name='q']")
    # # now search for "Nepal 2082 election"
    # search_box = page.query_selector("textarea[title='Search'], textarea[name='q']")
    # if search_box is None:
    #     print("Search box not found!")
    #     input("test")
    #     exit(1)
    # search_box.type("Nepal 2082 election")
    # search_box.press("Enter")
    # page.wait_for_load_state("networkidle")
    # title = page.title()
    # print(f"Search results page title: {title}")
    input("test")
