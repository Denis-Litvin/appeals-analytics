// Рисует графики из JSON, который сервер кладёт в <script id="charts-data">.
// Каждому графику соответствует <div id="chart-ИМЯ">. В customdata точки лежит ссылка на список обращений,
// клик по столбцу, сектору или точке переходит по ней.
(function () {
  var source = document.getElementById("charts-data");
  if (!source || !window.Plotly) {
    return;
  }

  // В пакете plotly нет русской локали, поэтому подписи панели и названия месяцев заданы здесь.
  Plotly.register({
    moduleType: "locale",
    name: "ru",
    dictionary: {
      "Autoscale": "Автомасштаб",
      "Box Select": "Выделение прямоугольником",
      "Compare data on hover": "Все значения при наведении",
      "Double-click to zoom back out": "Двойной клик возвращает масштаб",
      "Download plot": "Скачать график",
      "Download plot as a PNG": "Скачать график в PNG",
      "Lasso Select": "Выделение лассо",
      "Pan": "Сдвиг",
      "Reset axes": "Сбросить оси",
      "Reset view": "Сбросить вид",
      "Show closest data on hover": "Ближайшее значение при наведении",
      "Toggle Spike Lines": "Линии к осям",
      "Zoom": "Масштаб",
      "Zoom in": "Увеличить",
      "Zoom out": "Уменьшить",
    },
    format: {
      days: ["Воскресенье", "Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"],
      shortDays: ["Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"],
      months: ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
               "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"],
      shortMonths: ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"],
      date: "%d.%m.%Y",
      decimal: ",",
      thousands: " ",
    },
  });

  var charts = JSON.parse(source.textContent);
  var config = {
    displaylogo: false,
    responsive: true,
    locale: "ru",
    modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d"],
  };

  function linkOf(point) {
    var link = point.customdata;
    if (Array.isArray(link)) {
      link = link[0];
    }
    // Переходим только по своим адресам.
    return typeof link === "string" && link.charAt(0) === "/" ? link : null;
  }

  Object.keys(charts).forEach(function (name) {
    var element = document.getElementById("chart-" + name);
    if (!element) {
      return;
    }
    var chart = charts[name];
    Plotly.newPlot(element, chart.data, chart.layout, config);
    if (element.hasAttribute("data-click")) {
      element.on("plotly_click", function (event) {
        var link = event.points.length ? linkOf(event.points[0]) : null;
        if (link) {
          window.location.href = link;
        }
      });
    }
  });
})();
