FROM gcc:12

# 32-битная сборка: так адреса короче, а разбор стека в gdb нагляднее.
# gcc-multilib даёт -m32, gdb - отладчик, file - проверку типа бинарника.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       gdb gcc-multilib libc6-dev-i386 file python3 \
    && rm -rf /var/lib/apt/lists/*

# Файл, который читает учебная программа. В реальной системе его не должно
# быть в образе: здесь он нужен только чтобы fgets получил данные.
RUN mkdir -p /challenge/app-systeme/ch5 \
    && printf 'SECRET{format_string_lab}\n' > /challenge/app-systeme/ch5/.passwd

WORKDIR /lab
