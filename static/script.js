// DOM элементы
const messagesDiv = document.getElementById('messages');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const micBtn = document.getElementById('mic-btn');
const avatarImg = document.getElementById('avatar-img');

// Конфиг анимаций (загружается с сервера)
let animations = {};

// Состояние анимации (текущее)
let currentAnimation = 'idle';

// Настройки озвучки
let speechEnabled = true;  // озвучка включена по умолчанию
let lastReply = '';        // последний ответ бота для озвучки

// Загружаем конфиг анимаций при старте
fetch('/animations')
    .then(response => response.json())
    .then(config => {
        animations = config;
        setAnimation('idle');
    })
    .catch(err => console.error('Не удалось загрузить конфиг анимаций', err));

// Функция смены анимации
function setAnimation(state) {
    if (animations[state] && avatarImg.src !== animations[state]) {
        avatarImg.src = animations[state];
        currentAnimation = state;
    }
}

// Добавление сообщения в чат
function addMessage(text, sender) {
    const msgDiv = document.createElement('div');
    msgDiv.classList.add('message');
    msgDiv.classList.add(sender === 'user' ? 'user-message' : 'bot-message');
    msgDiv.textContent = text;
    messagesDiv.appendChild(msgDiv);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

// Озвучка текста
function speak(text) {
    if (!speechEnabled) return;
    if (!window.speechSynthesis) return;
    
    window.speechSynthesis.cancel(); // прерываем предыдущую речь
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'ru-RU';
    utterance.rate = 0.9;
    utterance.onstart = () => setAnimation('talking');
    utterance.onend = () => setAnimation('idle');
    utterance.onerror = () => setAnimation('idle');
    window.speechSynthesis.speak(utterance);
}

// Включение/выключение озвучки
function toggleSpeech() {
    speechEnabled = !speechEnabled;
    const btn = document.getElementById('speech-toggle-btn');
    if (btn) {
        btn.textContent = speechEnabled ? '🔊' : '🔇';
        btn.title = speechEnabled ? 'Озвучка включена' : 'Озвучка выключена';
    }
    if (!speechEnabled) {
        window.speechSynthesis.cancel();
        setAnimation('idle');
    }
}

// Озвучить последний ответ бота
function speakLastReply() {
    if (lastReply && speechEnabled) {
        speak(lastReply);
    } else if (!speechEnabled) {
        alert('Озвучка выключена. Нажмите кнопку 🔇, чтобы включить.');
    } else if (!lastReply) {
        alert('Нет сообщения для озвучки');
    }
}

// Отправка сообщения на сервер
async function sendMessage() {
    const message = userInput.value.trim();
    if (!message) return;

    addMessage(message, 'user');
    userInput.value = '';

    setAnimation('thinking');

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message })
        });
        const data = await response.json();
        addMessage(data.reply, 'bot');
        lastReply = data.reply;  // сохраняем для озвучки по кнопке
        setAnimation(data.animation || 'talking');
        setTimeout(() => setAnimation('idle'), 2000);
        // НЕ ОЗВУЧИВАЕМ АВТОМАТИЧЕСКИ
        // озвучка только по кнопке
    } catch (error) {
        console.error('Ошибка:', error);
        addMessage('Произошла ошибка при обращении к серверу.', 'bot');
        setAnimation('idle');
    }
}

// Голосовой ввод (Web Speech API)
function startListening() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        alert('Ваш браузер не поддерживает голосовой ввод');
        return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = 'ru-RU';
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
        setAnimation('listening');
    };

    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        userInput.value = transcript;
        sendMessage();
    };

    recognition.onerror = (event) => {
        console.error('Ошибка распознавания:', event.error);
        setAnimation('idle');
    };

    recognition.onend = () => {
        setAnimation('idle');
    };

    recognition.start();
}

// Добавляем кнопки управления озвучкой
function addSpeechControls() {
    const container = document.querySelector('.controls');
    if (!container) return;
    
    // Кнопка включения/выключения озвучки
    const toggleBtn = document.createElement('button');
    toggleBtn.id = 'speech-toggle-btn';
    toggleBtn.textContent = '🔊';
    toggleBtn.title = 'Озвучка включена';
    toggleBtn.classList.add('speech-toggle');
    toggleBtn.addEventListener('click', toggleSpeech);
    
    // Кнопка озвучить последний ответ
    const speakBtn = document.createElement('button');
    speakBtn.id = 'speak-last-btn';
    speakBtn.textContent = '🔈';
    speakBtn.title = 'Озвучить последний ответ';
    speakBtn.classList.add('speak-last');
    speakBtn.addEventListener('click', speakLastReply);
    
    container.appendChild(toggleBtn);
    container.appendChild(speakBtn);
}

// Инициализация после загрузки страницы
document.addEventListener('DOMContentLoaded', () => {
    addSpeechControls();
});

// Обработчики событий
sendBtn.addEventListener('click', sendMessage);
userInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendMessage();
});
micBtn.addEventListener('click', startListening);