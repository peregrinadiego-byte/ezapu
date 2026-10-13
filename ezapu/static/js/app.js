/* EZAPU · mejoras de interfaz (sin dependencias) */
(function () {
  "use strict";

  // 1 · Confirmación antes de eliminar
  document.addEventListener("submit", function (evento) {
    var formulario = evento.target;
    var mensaje = formulario.getAttribute("data-confirmar");
    if (mensaje && !window.confirm(mensaje)) {
      evento.preventDefault();
    }
  });

  // 2 · Total en vivo del editor de estimaciones
  var tabla = document.querySelector('input[name^="cantidad_"]');
  if (tabla) {
    var recalcular = function () {
      var total = 0;
      document.querySelectorAll('input[name^="cantidad_"]').forEach(function (entrada) {
        var precio = parseFloat(entrada.getAttribute("data-cantidad") || "0");
        var cantidad = parseFloat(entrada.value || "0");
        var importe = precio * cantidad;
        total += importe;
        var celda = entrada.closest("tr").cells[7];
        if (celda) {
          celda.textContent = importe.toLocaleString("es-MX", {
            minimumFractionDigits: 2, maximumFractionDigits: 2
          });
        }
      });
      var pie = document.querySelector("tfoot .der");
      document.querySelectorAll("tfoot th, tfoot td").forEach(function (celda) {
        if (celda.dataset.subtotal === "1") { celda.textContent = total.toFixed(2); }
      });
    };
    document.querySelectorAll('input[name^="cantidad_"]').forEach(function (entrada) {
      entrada.addEventListener("input", recalcular);
    });
  }

  // 3 · Selección rápida de proyecto en tablas largas
  document.querySelectorAll("table tbody tr").forEach(function (fila) {
    fila.addEventListener("dblclick", function () {
      var enlace = fila.querySelector("a.boton");
      if (enlace) { window.location.href = enlace.getAttribute("href"); }
    });
  });
})();
