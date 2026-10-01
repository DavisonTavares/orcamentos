import os
import django
import codecs
from django.core.management import call_command
from django.db import connection, connections
from django.db.migrations.executor import MigrationExecutor

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mundo_kids.settings')
django.setup()

print("=== MIGRAÇÃO INTELIGENTE SQLite → MySQL ===")

def check_schema_differences():
    """Verifica diferenças entre os esquemas SQLite e MySQL"""
    print("1. Verificando diferenças de esquema...")
    
    try:
        cursor_mysql = connection.cursor()
        cursor_sqlite = connections['sqlite_backup'].cursor()
        
        differences = []
        
        # Verificar tabelas existentes
        cursor_mysql.execute("SHOW TABLES")
        mysql_tables = {row[0] for row in cursor_mysql.fetchall()}
        
        cursor_sqlite.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        sqlite_tables = {row[0] for row in cursor_sqlite.fetchall()}
        
        missing_tables = sqlite_tables - mysql_tables
        if missing_tables:
            differences.append(f"Tabelas faltantes: {missing_tables}")
        
        # Verificar colunas em cada tabela comum
        common_tables = sqlite_tables.intersection(mysql_tables)
        for table in common_tables:
            # Colunas no MySQL
            cursor_mysql.execute(f"DESCRIBE {table}")
            mysql_columns = {row[0] for row in cursor_mysql.fetchall()}
            
            # Colunas no SQLite
            cursor_sqlite.execute(f"PRAGMA table_info({table})")
            sqlite_columns = {row[1] for row in cursor_sqlite.fetchall()}
            
            missing_columns = sqlite_columns - mysql_columns
            if missing_columns:
                differences.append(f"Tabela {table}: colunas faltantes {missing_columns}")
        
        return differences
        
    except Exception as e:
        print(f"❌ Erro ao verificar esquema: {e}")
        return ["Erro na verificação"]

def recreate_tables():
    """Recria todas as tabelas do zero"""
    print("2. Recriando estrutura do banco...")
    
    try:
        # 1. Fazer backup das migrações atuais
        cursor = connection.cursor()
        cursor.execute("SHOW TABLES")
        tables = [row[0] for row in cursor.fetchall()]
        
        if 'django_migrations' in tables:
            cursor.execute("CREATE TABLE IF NOT EXISTS django_migrations_backup AS SELECT * FROM django_migrations")
        
        # 2. Apagar e recriar o banco
        db_name = connection.settings_dict['NAME']
        cursor.execute(f"DROP DATABASE {db_name}")
        cursor.execute(f"CREATE DATABASE {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        cursor.execute(f"USE {db_name}")
        
        # 3. Recriar todas as migrações
        print("   Aplicando migrações...")
        call_command('migrate', database='default', fake=False)
        
        # 4. Restaurar registro de migrações se existir backup
        try:
            cursor.execute("CREATE TABLE IF NOT EXISTS django_migrations AS SELECT * FROM django_migrations_backup")
            cursor.execute("DROP TABLE django_migrations_backup")
        except:
            pass
            
        print("✅ Estrutura recriada com sucesso!")
        return True
        
    except Exception as e:
        print(f"❌ Erro ao recriar tabelas: {e}")
        return False

def migrate_data():
    """Migra os dados após garantir que a estrutura está correta"""
    
    # 3. Exportar dados do SQLite
    print("3. Exportando dados do SQLite...")
    try:
        call_command('dumpdata', 
                     database='sqlite_backup',
                     natural_foreign=True,
                     natural_primary=True,
                     indent=2,
                     output='migration_data.json')
        print("✅ Dados exportados")
    except Exception as e:
        print(f"❌ Erro na exportação: {e}")
        return False

    # 4. Corrigir encoding
    print("4. Corrigindo encoding...")
    try:
        with open('migration_data.json', 'r', encoding='latin-1') as f:
            content = f.read()
        with open('migration_data_fixed.json', 'w', encoding='utf-8') as f:
            f.write(content)
        print("✅ Encoding corrigido")
    except Exception as e:
        print(f"❌ Erro ao corrigir encoding: {e}")
        return False

    # 5. Importar dados
    print("5. Importando dados...")
    max_attempts = 2
    for attempt in range(max_attempts):
        try:
            if attempt == 0:
                call_command('loaddata', 'migration_data_fixed.json', database='default')
            else:
                call_command('loaddata', 'migration_data_fixed.json', database='default', ignorenonexistent=True)
            
            print("✅ Dados importados com sucesso!")
            return True
            
        except Exception as e:
            print(f"⚠️  Tentativa {attempt + 1} falhou: {e}")
            
            if attempt == 0 and "Unknown column" in str(e):
                print("   Detectado erro de estrutura, recriando tabelas...")
                if not recreate_tables():
                    return False
            else:
                if attempt == max_attempts - 1:
                    print("❌ Todas as tentativas falharam")
                    return False

def verify_migration():
    """Verifica se a migração foi bem-sucedida"""
    print("6. Verificando migração...")
    
    try:
        # Usar o custom user model correto
        from accounts.models import Usuario
        from orcamentos.models import Orcamento, Cliente
        
        user_count = Usuario.objects.using('default').count()
        user_count_sqlite = Usuario.objects.using('sqlite_backup').count()
        
        print(f"✅ MySQL: {user_count} usuários")
        print(f"✅ SQLite: {user_count_sqlite} usuários")
        
        # Verificar outras models importantes
        try:
            orcamento_count = Orcamento.objects.using('default').count()
            cliente_count = Cliente.objects.using('default').count()
            print(f"✅ Orçamentos: {orcamento_count}")
            print(f"✅ Clientes: {cliente_count}")
        except Exception as e:
            print(f"⚠️  Erro ao verificar outras models: {e}")
        
        if user_count == user_count_sqlite:
            print("🎉 Migração concluída com sucesso!")
            return True
        else:
            print("⚠️  Números diferentes - verifique manualmente")
            return False
            
    except Exception as e:
        print(f"❌ Erro na verificação: {e}")
        return False

# Execução principal
def main():
    # Verificar diferenças de esquema primeiro
    differences = check_schema_differences()
    
    if differences:
        print("❌ Diferenças encontradas:")
        for diff in differences:
            print(f"   - {diff}")
        
        resposta = input("Deseja recriar a estrutura do banco? (s/N): ")
        if resposta.lower() in ['s', 'sim', 'y', 'yes']:
            if not recreate_tables():
                return False
    else:
        print("✅ Esquemas compatíveis")
    
    # Migrar dados
    if migrate_data():
        return verify_migration()
    else:
        return False

if __name__ == "__main__":
    success = main()
    if success:
        print("\n=== MIGRAÇÃO CONCLUÍDA COM SUCESSO ===")
    else:
        print("\n=== MIGRAÇÃO FALHOU - VERIFIQUE OS ERROS ===")