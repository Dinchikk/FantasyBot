import time
import pandas as pd
import imgkit
import datetime
import os
from common import request_text_soup

# чемпионаты, которые мы хотим обработать
targetChamps = ['Беларусь']


# функция для вычисления сложности календаря
def difficulty_avg(t1, t2, side_match):
    # поправка на место проведения игры - высчитана средняя в среднем для крупных европейских чемпионатов
    side_eff = 0.4 * ((side_match == '(д)') - (side_match == '(г)'))
    # захардкоженные имена для нескольких клубов, для которых имена в разных местах на спортс.ру отличаются
    if t2 == 'Маритиму':
        t2 = 'Маритиму Мадейра'
    if t2 == 'Санта-Клара':
        t2 = 'Санта Клара'
    # tableDict - глобальный, для доступа к переменной из основной функции обработки
    try:
        diff = (tableDict['avg_g_scored'][t1] - tableDict['avg_g_against'][t1]) - (
                tableDict['avg_g_scored'][t2] - tableDict['avg_g_against'][t2])
        diff = side_eff + round(diff, 2)
        return diff
    except KeyError:
        print("Error with match ", t1, " - ", t2, ": unknown club")
        return 0


# функция для стайлинга - раскраски таблицы
def highlight_cells(value):
    par = []
    for i, op in enumerate(value):
        side_match = op[-3:]
        # первые 10 символов - дата в формете dd.mm.yyyy, последние 3 - сторона в формате (д)/(г)
        op = op[10:-3].strip()
        diff = difficulty_avg(value.index[i], op, side_match)
        if diff < -0.8:
            par.append('background-color: #CC0000')
        elif (diff >= -0.8) and (diff <= -0.3):
            par.append('background-color: #CC6600')
        elif (diff >= -0.3) and (diff <= 0.4):
            par.append('background-color: #FFFF19')
        elif (diff >= 0.4) and (diff <= 1):
            par.append('background-color: #88CC00')
        else:
            par.append('background-color: #009900')
    return par


# сокращение "В гостях" или "Дома" до простых "(д)" и "(г)"
def side_map(side):
    return '(' + side.split(' ')[-1][0].lower() + ')'


# объявлен глобально, чтобы быть доступным в функции стайлинга таблицы
tableDict = {}


def calendar_processing(current_champ, current_champ_links):
    # логирование информации о времени обработки каждого чемпионата
    champ_start_time = time.time()
    current_champ_link = current_champ_links['sports']
    if not current_champ_link:
        print('Для данного чемпионата календарь недоступен, обработка календаря пропускается...')
        return
    current_table_link = current_champ_link + 'table/'
    # получаем страницу с таблицей обрабатываемого чемпионата
    _, table_soup = request_text_soup(current_table_link)
    # выделение таблицы со страницы
    table_body = table_soup.tbody
    team_body_list = table_body.find_all('tr')
    # колонки футбольных таблиц на sports.ru - численные атрибуты каждой команды
    table_columns = ["games", "won", "draw", "lost", "g_scored", "g_against", "points"]
    team_links = {}
    # работаем с глобальным словарем tableDict
    global tableDict
    tableDict = {}
    # для каждой команды из таблицы сохраним ссылку на профиль команды, все численные атрибуты
    for team in team_body_list:
        team_name = team.find('a', class_='name').get('title')
        team_links[team_name] = team.find('a', class_='name').get('href')
        team_numbers = team.find_all('td', class_=None)
        for j, n in enumerate(team_numbers):
            team_numbers[j] = int(n.text)
        tableDict[team_name] = dict(zip(table_columns, team_numbers))
        tableDict[team_name]['avg_g_scored'] = tableDict[team_name]["g_scored"] / tableDict[team_name]["games"]
        tableDict[team_name]['avg_g_against'] = tableDict[team_name]["g_against"] / tableDict[team_name]["games"]
    # транспонируем этот словарь, чтобы иметь доступ в другом порядке
    # (вместо team_name -> games -> 5 получаем games -> team_name -> 5)
    tableDict = dict(pd.DataFrame(tableDict).transpose())

    # обработка календаря для каждой команды
    champ_calendar_dict = {}
    for team, team_link in team_links.items():
        team_link = team_link + 'calendar'
        # запрос страницы с календарем для каждой команды
        ''' (в теории можно обрабатывать через календарь соревнования)
        (НО - на спортс в таком случае не обязательна сортировка по дате 
        - используется сортировка по ФОРМАЛЬНОМУ туру)'''
        _,  calendar_team_soup = request_text_soup(team_link)
        # выцепление самой таблицы с календарем матчей
        calendar_team_body = calendar_team_soup.find('tbody')
        # получение списка матчей
        match_team_list = calendar_team_body.find_all('tr')

        date = []
        competition = []
        opponent = []
        side = []
        result = []
        for match in match_team_list:
            # убираем из рассмотрения матчи с пометкой "перенесен" вместо даты
            if 'перенесен' not in str(match):
                date.append(match.find('a').text.split('|')[0].strip())
                competition.append(match.div.a.get('href'))
                opponent.append(match.find_all('div')[1].text.strip())
                side.append(side_map(match.find('td', class_="alRight padR20").text))
                result.append(match.find('a', class_='score').text.strip())

        # формирование календаря в формате лист в листе
        team_calendar = [[date[i] + ' ' + opponent[i] + side[i],
                         competition[i]] for i in range(0, len(opponent))]
        # выделение календаря будущих игр - их мы находим по наличию ссылки на превью вместо счета
        future_team_calendar = team_calendar[result.index('превью'):]
        # берем из списка будущих игр только те, которые будут проходить в интересующем нас чемпионате
        # для проверки используем ссылку на чемпионат из нашего маппинга, сравнивая ее со ссылкой на
        # чемпионат, который соответствует обрабатываемой игре
        future_team_calendar_champ = list(filter(lambda x: current_champ_link in x[1], future_team_calendar))
        # взятие ближайших 5 игр для каждой команды
        champ_calendar_dict[team] = dict(zip(['1', '2', '3', '4', '5'],
                                               [future_team_calendar_champ[x][0] for x in range(5)]))
    # транспонирование таблицы
    champ_calendar = pd.DataFrame(champ_calendar_dict).transpose()
    # оформление и сохранение
    champ_calendar_style = champ_calendar.style.apply(highlight_cells)
    html = champ_calendar_style.render()
    path_wkthmltoimage = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltoimage.exe'
    config = imgkit.config(wkhtmltoimage=path_wkthmltoimage)
    options = {'encoding': "UTF-8"}
    # создание директории при отсутствии оной
    directory = ("pics/" + str(datetime.datetime.now().date()) + "/calendars/")
    if not os.path.isdir(directory):
        os.makedirs(directory)
    imgkit.from_string(html, directory + current_champ + ".png", config=config, options=options)

    # логирование времени обработки каждого чемпионата
    print('Календарь чемпионата "' + current_champ + '" обработан, время обработки: '
          + str(round(time.time() - champ_start_time, 3)) + "s")
