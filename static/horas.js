// Campo de tempo de voo: coloca os dois pontos sozinho enquanto a pessoa digita.
// Ex: digitar 0130 mostra 01:30. Quem digita em horas decimais (1,5) não é alterado.
document.addEventListener('input', function (evento) {
    var campo = evento.target;
    if (!campo.classList || !campo.classList.contains('campo-horas')) return;
    if (!/^[0-9:]*$/.test(campo.value)) return;
    var digitos = campo.value.replace(/[^0-9]/g, '').slice(0, 4);
    campo.value = digitos.length >= 3 ? digitos.slice(0, -2) + ':' + digitos.slice(-2) : digitos;
});
