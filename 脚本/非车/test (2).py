try:
    path = "UI测试.xls"
    sheet_name = "ui_sheet"
    driver = webdriver.Chrome()
    driver.implicitly_wait(10)
    url = readByRowName(path, sheet_name, "url")
    driver.get(url)
    sleep(3)
    driver.find_element_by_class_name("immediate-offer").click()
    driver.switch_to.frame("showIframecarIndexNew")
    driver.find_element_by_id("citynameS").click()
    driver.switch_to.frame("overPageIframe")
except:
    raise RuntimeError(traceback)
finally:
    driver.quit()